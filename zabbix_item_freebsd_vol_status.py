
import subprocess
import argparse

_FILE_VER = "to_be_filled_by_CI"


class VolStatus:
    """
    Base class

    >>> VolStatus().get_zabbix_item()
    'OK'
    """

    def __init__(self):
        self.command = None
        self.command_rv = None
        self.status = {
            "devs_problem": [],
            "success": False,
            "error": "Command hasn't been run"
        }

    def run_command(self):
        if self.command is not None:
            self.command_rv = subprocess.run(self.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                             encoding="ascii")

    def parse_command_rv(self):
        self.status = {
            "devs_problem": [],
            "success": True,
            "error": None
        }

    def get_status(self):
        if self.status["success"]:
            if len(self.status["devs_problem"]):
                return "PROBLEM", ", ".join(self.status["devs_problem"])
            else:
                return "OK",
        else:
            return "FAIL", self.status["error"]

    def get_zabbix_item(self):
        self.run_command()
        self.parse_command_rv()
        s = self.get_status()
        if s[0] == "OK":
            return s[0]
        else:
            return "{}: {}".format(s[0], s[1])


class ZfsVolStatus(VolStatus):
    """
    ZFS class

    >>> ZfsVolStatus().get_zabbix_item()
    'OK'
    """

    def __init__(self):
        VolStatus.__init__(self)
        self.command = "zpool", "get", "-H", "health"

    def parse_command_rv(self):
        if self.command_rv is not None:
            if self.command_rv.returncode == 0:
                for line in self.command_rv.stdout.split(sep="\n"):
                    if len(line) > 0 and not line.isspace():
                        dev_info = line.split()
                        if dev_info[2] != "ONLINE":
                            self.status["devs_problem"].append(dev_info[0])
                self.status["success"] = True
            else:
                self.status["error"] = self.command_rv.stderr


class GmirrorVolStatus(VolStatus):
    """
    Gmirror class

    >>> GmirrorVolStatus().get_zabbix_item()
    'OK'
    """

    def __init__(self):
        VolStatus.__init__(self)
        self.command = "gmirror", "status", "-s"

    def parse_command_rv(self):
        if self.command_rv is not None:
            if self.command_rv.returncode == 0:
                for line in self.command_rv.stdout.split(sep="\n"):
                    if len(line) > 0 and not line.isspace():
                        dev_info = line.split()
                        if dev_info[1] != "COMPLETE" and dev_info[0] not in self.status["devs_problem"]:
                            self.status["devs_problem"].append(dev_info[0])
                self.status["success"] = True
            else:
                self.status["error"] = self.command_rv.stderr


if __name__ == "__main__":
    defaults = {
        "getters": {
            "zfs": ZfsVolStatus,
            "gmirror": GmirrorVolStatus
        }
    }
    cmd = argparse.ArgumentParser(description="Volume status getter")
    cmd.add_argument("-version", action="version", version=_FILE_VER)
    cmd.add_argument("-type", help="Volume type ({})".format(", ".join(sorted(defaults["getters"].keys()))),
                     metavar="name", choices=defaults["getters"].keys(), required=True)
    cmdargs = cmd.parse_args()
    print(defaults["getters"][cmdargs.type]().get_zabbix_item(), end="")
