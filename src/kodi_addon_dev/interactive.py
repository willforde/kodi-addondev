# Standard Library Imports
from typing import Union, List, Tuple, Type, Callable
import multiprocessing as mp
from copy import deepcopy
import argparse
import runpy
import sys

# Package imports
from kodi_addon_dev import displays
from kodi_addon_dev.repo import LocalRepo
from kodi_addon_dev.support import Addon, logger
from kodi_addon_dev.tesseract import Tesseract, KodiData
from kodi_addon_dev.utils import urlparse
import xbmcgui
import xbmc


def subprocess(pipe, reuse):  # type: (mp.connection, bool) -> None
    try:
        # Wait till we receive
        # commands from the executer
        while True:
            # Stop the subprocess
            # This is required when reusing the subprocess
            command, data = pipe.recv()  # type: (str, Tuple[Addon, List[str], LocalRepo, urlparse.SplitResult])
            if command == "stop":
                break

            # Execute the addon
            elif command == "execute":
                addon, deps, cached, url = data
                # Patch sys.argv to emulate what is expected
                urllist = [url.scheme, url.netloc, url.path, "", ""]
                sys.argv = (urlparse.urlunsplit(urllist), 1, "?{}".format(url.query))

                try:
                    # Create tesseract to handle kodi module interactions
                    xbmc.session = tesseract = Tesseract(addon, deps, cached, pipe=pipe)
                    tesseract.data.path = url.geturl()

                    # Execute the addon
                    module = addon.entrypoint[1]
                    runpy.run_module(module, run_name="__main__", alter_sys=False)

                # Addon must have directly raised an error
                except Exception as e:
                    logger.debug(e, exc_info=True)
                    pipe.send((False, False))

                else:
                    # Send back the results from the addon
                    resp = (tesseract.data.succeeded, tesseract.data)
                    pipe.send(resp)

            # If this subprocess will not be reused then
            # break from loop to end the process
            if reuse is False:
                break
    except KeyboardInterrupt:
        pipe.send((False, False))

    except Exception as e:
        logger.error(e, exc_info=True)
        pipe.send((False, False))


class PRunner(object):
    def __init__(self, cached, addon, user_input):  # type: (LocalRepo, Addon, Callable) -> None
        self.deps = cached.load_dependencies(addon)
        self.reuse = addon.reuse_lang_invoker
        self.user_input = user_input
        self.cached = cached
        self.addon = addon

        # Pipes to handle passing of data to and from the subprocess
        self.pipe, self.sub_pipe = mp.Pipe(duplex=True)
        self._process = None  # type: mp.Process

    @property
    def process(self):  # type: () -> mp.Process
        if self._process and self._process.is_alive():
            logger.debug("Reuseing subprocess: %s", self._process.name)
            return self._process
        else:
            # Create the new process that will execute the addon
            process = mp.Process(target=subprocess, args=[self.sub_pipe, self.reuse])
            process.start()

            logger.debug("Spawned new subprocess: %s", process.name)

            if self.reuse:
                # Save the process for later use
                self._process = process
            return process

    def execute(self, url):  # type: (urlparse.SplitResult) -> Union[KodiData, bool]
        logger.info("Execution Addon: id=%s path=%s query=%s", url.netloc, url.path, url.query)
        try:
            # Construct command and send to sub process for execution
            command = ("execute", (self.addon, self.deps, self.cached, url))
            process, pipe = self.process, self.pipe
            pipe.send(command)

            # Wait till we receive data from the addon process
            while process.is_alive():
                # Wait to receive data from pipe before continuing
                # If no data was received within one second, check
                # to make sure that the process is still alive
                if pipe.poll(1):
                    status, data = pipe.recv()
                else:
                    continue

                # Check if user input is requested
                if status == "prompt":
                    # Prompt the user for input and
                    # send it back to the subprocess
                    input_data = self.user_input(data)
                    pipe.send(input_data)

                else:
                    # Check if execution failed before returning
                    return False if status is False else data

        except Exception as e:
            logger.error(e, exc_info=True)

        # SubProcess exited unexpectedly
        return False

    def stop(self):
        """Stop the subproces."""
        if self._process and self._process.is_alive():
            logger.debug("Terminating process: %s", self._process.name)
            stop_command = ("stop", None)
            self.pipe.send(stop_command)
            self._process.join()


class PManager(dict):
    def __init__(self, cached, user_input):  # type: (LocalRepo, Callable) -> None
        super(PManager, self).__init__()
        self.user_input = user_input
        self.cached = cached

    def __missing__(self, addon):  # type: (Addon) -> PRunner
        self[addon] = runner = PRunner(self.cached, addon, self.user_input)
        return runner

    def close(self):
        """Stop all saved runners"""
        for runner in self.values():
            runner.stop()


class Interact(object):
    def __init__(self, cmdargs, cached, display=None):
        # type: (argparse.Namespace, LocalRepo, Type[displays.BaseDisplay]) -> None

        self.parent_stack = []  # type: List[KodiData]
        self.cached = cached
        self.args = cmdargs

        # Use custom display object if one is given, else
        # Use the pretty terminal display if possible, otherwise use the basic non tty display
        display = display if display else displays.CMDisplay
        self.display = display(cached, cmdargs)

        # The process manager
        self.pm = PManager(cached, self.display.input)

        # Reverse the list of preselection for faster access
        self.preselect = list(map(int, cmdargs.preselect))
        self.preselect.reverse()

        # Log the arguments pass to program
        logger.debug("Command-Line Arguments: %s", vars(cmdargs))

    def start(self, request):  # type: (Union[KodiData, urlparse.SplitResult]) -> None
        try:
            while request:
                if isinstance(request, urlparse.SplitResult):
                    # Request the addon & process manager related to the kodi plugin id
                    addon = self.cached.request_addon(request.netloc)
                    if addon.entrypoint is None:
                        request = self.handle_failed("Sorry, Only Video/Music/Picture add-on's are supported")
                        continue
                    else:
                        runner = self.pm[addon]  # type: PRunner

                    # Execute addon in subprocess
                    resp = runner.execute(request)
                    if resp is False:
                        request = self.handle_failed("Failed to execute addon. Please check log.")
                        continue
                else:
                    # This must be the parent object
                    resp = request

                # Process the response and convert into a list of items
                items = self.process_resp(resp)
                selector = self.preselect.pop() if self.preselect else self.display.show_raw(items, resp.path)

                # Fetch the selected listitem and start the loop again
                if selector == 0 and self.parent_stack:
                    request = self.parent_stack.pop()
                elif selector is None:
                    break
                else:
                    # Return preselected item or ask user for selection
                    item = items[selector]
                    path = item["path"]

                    # Split up the kodi url
                    resp.calling_item = deepcopy(item)
                    self.parent_stack.append(resp)
                    request = urlparse.urlsplit(path)

        except KeyboardInterrupt:
            pass

        except Exception as e:
            logger.error(e, exc_info=True)
            self.display.notify("Sorry :(, Something went really wrong.", skip=False)

        # Stop all stored saved processes
        self.pm.close()

    def handle_failed(self, msg):  # type: (str) -> Union[KodiData, bool]
        """
        Report to user that addon has failed to execute.
        Returning previous list if one exists.
        """
        ret = self.display.notify(msg)
        logger.error(msg)
        return self.parent_stack.pop() if self.parent_stack else False if ret else False

    def process_resp(self, resp):  # type: (KodiData) -> List[xbmcgui.ListItem]
        """Process the resp object and trun into a list of listitems."""

        # Fist item must be the parent caller if this resp is a child response
        items = [{"label": "..", "path": self.parent_stack[-1].path}] if self.parent_stack else []

        # Populate list of items
        if resp.listitems:
            items.extend(item[1] for item in resp.listitems)
        elif resp.resolved:
            # Add resolved video
            if self.parent_stack:
                base = self.parent_stack[-1].calling_item
                base.pop("context", "")
                base.update(resp.resolved)
                items.append(base)
            else:
                items.append(resp.resolved)

            # Add the playlist
            items.extend(resp.playlist)

        # Return the full list of listitems
        return items
