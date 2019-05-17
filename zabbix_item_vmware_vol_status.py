
import subprocess
import argparse

_FILE_VER = "to_be_filled_by_CI"


class VolStatusException(Exception):
    def __init__(self, msg=None):
        self.msg = msg

class ParserException(VolStatusException):
    pass

class ReviewerException(VolStatusException):
    pass

class VolStatus:
    """
    Base class

    >>> VolStatus().get_zabbix_item()
    'OK'
    """

    def __init__(self):
        # self.command is a chain of commands to be executed to get the volume status.
        # Command entry is a dict of 3 or 4 items:
        # {"tag": "some_tag", "txt": "a_command_itself", "cwd": "an optional working dir",
        # "parser": parser_routine_name}.
        # self.command is a list of command entries to be executed and parsed.
        self.command = [{"tag": "base", "txt": "hostname", "parser": self.command_base_command}]

        # self.command_rv is a dict of data blocks returned by commands. Its keys are tags of commands.
        # Command rv entry is a dict of a command return code ("_rc"), STDOUT ("_stdout"), STDERR (_stderr),
        # and any vars (keys) which are returned by a parser routine.
        self.command_rv = {"base": {}}

        # Status is the final status of a whole command chain
        # If a step fails, the execution stops. error_tag and error are filled with tag and STDERR of the failed step.
        self.status = {
            "devs_problem": [],
            "success": False,
            "error_tag": None,
            "error": "Command hasn't been run"
        }

    def review_chain(self):
        """
        Check the first element (by its tag) of the chain and modifies it (edits, removes, adds elements) taking into
        account the data that is in the self.command_rv.
        :return: None
        """
        pass

    def run_chain(self):
        while True:
            try:
                c = self.command.pop(0)
            except IndexError:
                break
            else:
                if c["txt"] is not None:
                    command_rv = subprocess.run(c["txt"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                                cwd=c.get("cwd", None), encoding="ascii")
                    self.command_rv[c["tag"]]["_rc"] = command_rv.returncode
                    self.command_rv[c["tag"]]["_stdout"] = command_rv.stdout
                    self.command_rv[c["tag"]]["_stderr"] = command_rv.stderr
                    if self.command_rv[c["tag"]]["_rc"] == 0:
                        try:
                            self.command_rv[c["tag"]].update(c["parser"](c["tag"]))
                        except ParserException as ex:
                            self.status["success"] = False
                            self.status["error_tag"] = c["tag"]
                            self.status["error"] = "parser failed: {}".format(ex.msg)
                            break
                    else:
                        self.status["success"] = False
                        self.status["error_tag"] = c["tag"]
                        self.status["error"] = command_rv.stderr
                        break
                    self.status["success"] = True
            self.review_chain()

    def get_status(self):
        if self.status["success"]:
            if len(self.status["devs_problem"]):
                return "PROBLEM", ", ".join(self.status["devs_problem"])
            else:
                return "OK",
        else:
            return "FAIL", self.status["error_tag"], self.status["error"]

    def get_zabbix_item(self):
        self.run_chain()
        s = self.get_status()
        if s[0] == "OK":
            return s[0]
        else:
            return "{}: {}: {}".format(s[0], s[1], s[2])

    def command_base_command(self, tag):
        return {}


class LSIVolStatus(VolStatus):
    """
    LSI class

    >>> LSIVolStatus().get_zabbix_item()
    'OK'
    """

    def __init__(self, clipath=None):
        VolStatus.__init__(self)
        self.command = [
            {
                "tag": "count",
                "txt": ("./storcliKL", "show", "ctrlcount"),
                "cwd": clipath,
                "parser": self.command_count
            },
            {
                "tag": "show_{}",
                "txt": ("./storcliKL", "/c{}/vall", "show"),
                "cwd": clipath,
                "parser": self.command_show
            }
        ]
        self.command_rv = {"count": {}, "show_{}": {}}

    def review_chain(self):
        if len(self.command):
            if self.command[0]["tag"] == "show_{}":
                newcommand = []
                try:
                    for c in range(self.command_rv["count"]["count"]):
                        newcommand.append(
                            {
                                "tag": self.command[0]["tag"].format(c),
                                "txt": (self.command[0]["txt"][0],
                                        self.command[0]["txt"][1].format(c),
                                        self.command[0]["txt"][2]),
                                "cwd": self.command[0]["cwd"],
                                "parser": self.command[0]["parser"]
                            }
                        )
                        self.command_rv[self.command[0]["tag"].format(c)] = {}
                except KeyError:
                    raise ReviewerException("Could not review tag \"show\": no \"count\" data found")
                else:
                    del(self.command[0])
                    self.command = newcommand + self.command
                    del(self.command_rv["show_{}"])

    def command_count(self, tag):
        for line in self.command_rv[tag]["_stdout"].split(sep="\n"):
            if line.startswith("Controller Count"):
                return {"count": int(line.split("=")[1].strip())}
        raise ParserException("expected line not found")

    def command_show(self, tag):
        anchor = {"count": 0, "expected": 2}
        anchor_found = False
        for line in self.command_rv[tag]["_stdout"].split(sep="\n"):
            if anchor["count"] == anchor["expected"]:
                anchor_found = True
                if line.startswith("-----"):
                    break
                else:
                    dev_data = line.split()
                    dev_dg, dev_vd, dev_state = dev_data[0].split("/") + [dev_data[2]]
                    if dev_state != "Optl":
                        self.status["devs_problem"].append("C{}DG{}VD{}".format(tag.split("_")[-1], dev_dg, dev_vd))
            elif anchor["count"] == 0 and line.startswith("DG/VD"):
                anchor["count"] += 1
            elif anchor["count"] == 1 and line.startswith("-----"):
                anchor["count"] += 1
            else:
                anchor["count"] = 0
        if not anchor_found:
            raise ParserException("expected anchor not found")
        return {}


if __name__ == "__main__":
    defaults = {
        "getters": {
            "lsi": LSIVolStatus
        }
    }
    cmd = argparse.ArgumentParser(description="Volume status getter")
    cmd.add_argument("-version", action="version", version=_FILE_VER)
    cmd.add_argument("-type", help="Volume type ({})".format(", ".join(sorted(defaults["getters"].keys()))),
                     metavar="name", choices=defaults["getters"].keys(), required=True)
    cmd.add_argument("-clipath", help="Path to the CLI utility", metavar="path")
    cmdargs = cmd.parse_args()
    print(defaults["getters"][cmdargs.type](cmdargs.clipath).get_zabbix_item(), end="")
