#!/usr/bin/env/python3
"""An inheritable command line interface generator inspired by cmd.py."""
from inspect import getmembers, ismethod, signature
from enum import Enum
import readline
from sys import stdin, stdout

def cli_method(func):
    """Decorator to register method as available to the CLI."""
    func.is_cli_method = True
    return func


class IntrospectCLI(object):
    """A simple framework for writing line-oriented command interpreters.

    These are often useful for test harnesses, administrative tools, and
    prototypes that will later be wrapped in a more sophisticated interface.

    A Cmd instance or subclass instance is a line-oriented interpreter
    framework.  There is no good reason to instantiate Cmd itself; rather,
    it's useful as a superclass of an interpreter class you define yourself
    in order to inherit Cmd's methods and encapsulate action methods.

    """
    prompt = ">>>"
    ruler = '='
    nohelp = "*** No help on %s"
    use_rawinput = True
    complete_key = 'tab'
    DELIM = ' '


    def __init__(self):
        """collect functions."""
        self.cli_methods = self._get_cli_methods()
        self.cli_method_definitions = self._get_cli_method_definitions()
        import pprint
        pprint.pprint(self.cli_method_definitions)


    def _get_cli_methods(self):
        cli_methods = {}

        # Collect all methods that have the is_cli_method as an attribute
        cli_methods = {m[0]:m[1] for m in getmembers(self)
                        if ismethod(getattr(self, m[0]))
                        and hasattr(m[1], 'is_cli_method')}

        return cli_methods

    def _get_cli_method_definitions(self):
        """Build method definitions. Thank you Jacob!

        Returns:
            Dictionary of method names mapped to their definitions.
        """
        definitions = {}

        for method_name, method in self.cli_methods.items():
            parameters = {}
            sig = signature(method)

            # FIXME: how does this code hande functions wrapped in decorators??
            # Collapse to the function any wrapped functions.
            # This works only for function decorator wrappers using
            # functools.wraps to do the wrapping
            #while hasattr(method, "__wrapped__"):
            #    method = method.__wrapped__

            for parameter_name in sig.parameters:
                #if parameter_name == "self":
                #    continue
                parameter = {}
                parameter_type = None
                parameter_sig = sig.parameters[parameter_name]
                if parameter_sig.annotation is not parameter_sig.empty:
                    parameter_type = parameter_sig.annotation
                parameter["type"] = parameter_type.__name__ if parameter_type is not None else None
                if parameter_sig.default is not parameter_sig.empty:
                    parameter["default"] = parameter_sig.default
                if parameter_type is not None and issubclass(parameter_type, Enum):
                    parameter["type"] = "Enum"
                    parameter["options"] = list(parameter_type.__members__.keys())

                parameters[parameter_name] = parameter

            definitions[method_name] = {
                "parameters": parameters,
                "doc": method.__doc__
            }

        return definitions

    def complete_call(self):
        """complete the function call based on method definition content."""
        pass

    def display_help(self):
        """display help for a given function."""
        pass

    @cli_method
    def help(self, func_name):
        """Display usage for a particular function."""
        print(self.cli_method_definitions[func_name]["doc"])

    def complete(self, text, state, *args, **kwargs):
        """function invoked for completing partially-entered text.
        Formatted according to readline's set_completer spec:
        https://docs.python.org/3/library/readline.html#completion

        Note: this fn gets called by readline really weirdly.
        This fn gets called repeatedly with increasing values of state until
        the fn returns None.
        """
        text = text.lstrip() # what we are matching against
        line = readline.get_line_buffer() # The whole line.
        cmd_with_args = line.split()

        if len(cmd_with_args) <= 1 and line[-1] is not self.__class__.DELIM:
            # Return matches but omit match if it is fully-typed.
            results = [fn for fn in self.cli_methods.keys() if fn.startswith(text) and fn != text]
            return results[state]

        func_name = cmd_with_args[0]
        func_params = \
            [p for p in self.cli_method_definitions[func_name]['parameters'].keys()
             if p.startswith(text) and p != text]
        return func_params[state]


    def cmdloop(self, intro=None):
        """Repeatedly issue a prompt, accept input, parse an initial prefix
        off the received input, and dispatch to action methods, passing them
        the remainder of the line as argument.

        """

        readline.set_completer(self.complete)
        readline.parse_and_bind(f"{self.__class__.complete_key}: complete")
        stop = False
        while not stop:
            try:
                line = input(self.prompt)
                #stdout.write(self.prompt)
                #stdout.flush()
                #line = stdin.readline()
            except EOFError:
                line = 'EOF'
            #stop = self.onecmd(line)
            print(f"Executing {line}")
