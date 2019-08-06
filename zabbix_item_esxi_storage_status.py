
import argparse
import os
import sys
from pyVim import connect
# from pyVmomi import vmodl
from pyVmomi import vim

_FILE_VER = "to_be_filled_by_CI"


def make_filename(path, argv_0=sys.argv[0]):
    """
    :param path: Relative to app's dir of full file path
    :param argv_0: Path to script
    :return: Actual file path
    """
    if os.path.isabs(path):
        return path
    else:
        return os.path.normpath(os.path.join(os.path.dirname(argv_0), path))


class ConnInfo:

    def __init__(self, host, user, password, port=443, verifycert=False):
        self.host = host
        self.user = user
        self.password = password
        self.port = port
        self.verifycert = verifycert


class StorageStatus:
    """
    Base class
    """

    def __init__(self, conninfo):
        self.conninfo = conninfo
        self.connected = False
        self.service_instance = None
        self.sGreen = "Green"    # vSphere "Green"
        self.sYellow = "Yellow"  # vSphere "Yellow"
        self.status = {
            "devs_problem_red": [],
            "devs_problem_yellow": [],
            "success": False,
            "error": "Status hasn't been fetched yet"
        }

    def connect(self, conninfo):
        pass

    def __del__(self):
        if self.connected:
            self.disconnect()

    def disconnect(self):
        pass

    def get_data(self):
        self.status = {
            "devs_problem": [],
            "success": True,
            "error": None
        }

    def get_status(self):
        if self.status["success"]:
            if len(self.status["devs_problem_red"]):
                return "PROBLEM", ", ".join(self.status["devs_problem_red"] + self.status["devs_problem_yellow"])
            elif len(self.status["devs_problem_yellow"]):
                return "WARNING", ", ".join(self.status["devs_problem_yellow"])
            else:
                return "OK",
        else:
            return "FAIL", self.status["error"]

    def get_zabbix_item(self):
        self.connect(self.conninfo)
        if self.connected:
            self.get_data()
        s = self.get_status()
        if s[0] == "OK":
            return s[0]
        else:
            return "{}: {}".format(s[0], s[1])


class ESXiStorageStatus(StorageStatus):
    """
    ESXi class
    """

    def __init__(self, host, user, password, port=443, verifycert=False):
        StorageStatus.__init__(self, conninfo=ConnInfo(host, user, password, port, verifycert))

    def connect(self, conninfo):
        if conninfo.verifycert:
            connect_func = connect.SmartConnect
        else:
            connect_func = connect.SmartConnectNoSSL
        try:
            self.service_instance = connect_func(host=conninfo.host, user=conninfo.user, pwd=conninfo.password,
                                                 port=conninfo.port)
        except Exception as e:
            self.status["error"] = "Could not connect to ESXi host: {}".format(str(e))
        else:
            self.connected = True

    def disconnect(self):
        connect.Disconnect(self.service_instance)

    def get_data(self):
        try:
            content = self.service_instance.RetrieveContent()
            view = content.viewManager.CreateContainerView(content.rootFolder, [vim.HostSystem], True)
            for item in view.view:
                item.configManager.serviceSystem.RefreshServices()
                for info in item.runtime.healthSystemRuntime.hardwareStatusInfo.storageStatusInfo:
                    # We use status.label below because it is a property of the ancestor: Description.
                    # There is also status.key that seems the same. But we don't use it because this is a property of
                    # ElementDescription which inherits Description.
                    if info.status.label == self.sYellow:
                        self.status["devs_problem_yellow"].append(info.name)
                    elif info.status.label != self.sGreen:
                        # We are not sure so far if there are any other statuses but Green and Yellow.
                        # So we treat anything else Red.
                        self.status["devs_problem_red"].append(info.name)
        except Exception as e:
            self.status["error"] = "Could not fetch volume status: {}".format(str(e))
        else:
            self.status["success"] = True


if __name__ == "__main__":
    cmd = argparse.ArgumentParser(description="ESXi storage status getter")
    cmd.add_argument("-version", action="version", version=_FILE_VER)
    cmd.add_argument("-host", help="ESXi host name", metavar="NAME_OR_IP", required=True)
    cmd.add_argument("-userpass", help="file with user/password", metavar="FILE_NAME (work dir related)", required=True)
    cmd.add_argument("-port", help="ESXi host's port (443)", metavar="NUMBER", type=int, default=443)
    cmd.add_argument("-verifycert", help="Verify the host's SSL sert (False)", action="store_true", default=False)
    cmdargs = cmd.parse_args()
    lines = []
    for line in open(make_filename(cmdargs.userpass), newline="\n"):
        lines.append(line.strip())
    cmdargs.user, cmdargs.password = lines[0:2]
    print(ESXiStorageStatus(
        cmdargs.host,
        cmdargs.user,
        cmdargs.password,
        cmdargs.port,
        cmdargs.verifycert).get_zabbix_item(), end="")
