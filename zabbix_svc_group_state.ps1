param(
    [Parameter(Mandatory=$true, HelpMessage="Svc group's name", ParameterSetName="Normal")]
    [string]
    $SGroupName,
    [Parameter(HelpMessage="Svc name regex", ParameterSetName="Normal")]
    [string]
    $SNameRegex,
    [Parameter(HelpMessage="Svc names list", ParameterSetName="Normal")]
    [string]
    $SNameList,
    [Parameter(HelpMessage="File with svc names list", ParameterSetName="Normal")]
    [string]
    $SNameListFile,
    [Parameter(HelpMessage="Type of info to be returned", ParameterSetName="Normal")]
    [ValidateSet("item", "trapper", "discovery")]
    [string]
    $RTType="trapper",
    [Parameter(HelpMessage="Get script's version", ParameterSetName="Version")]
    [switch]
    [Alias("v")]
    $version
)
$ErrorActionPreference = "Stop"

$_FILE_VER = "to_be_filled_by_CI"
if ($version) {
    $_FILE_VER
    exit
}

$statuses = @(
    "Running",
    "StartPending",
    "ContinuePending",
    "PausePending",
    "StopPending",
    "Paused",
    "Stopped"
)
$statuses_h = @{}
$i = 0
foreach ($status in $statuses) {
    $statuses_h[$status] = $i++
}
$statuses = $statuses_h

if ($PSBoundParameters.ContainsKey("SNameRegex")) {
    $svcnames = @((Get-Service | Where-Object {$_.Name -imatch $SNameRegex}).Name)
}
else {
    $svcnames = @()
}
if ($PSBoundParameters.ContainsKey("SNameList")) {
    $svcnames += @($SNameList)
}
if ($PSBoundParameters.ContainsKey("SNameListFile")) {
    $svcnames += @(Get-Content $SNameListFile)
}

$worst = "Notfound"
$services = [System.Collections.ArrayList] @()
foreach ($svc in $(Get-Service|Where-Object {$_.Name -in $svcnames -and $_.StartType -in ("automatic", "manual")})) {
    $status_str = [string] $svc.status
    [void] $services.Add(@{'{#SERVICE.NAME}'=$svc.Name; '{#SERVICE.STARTTYPE}'=[string] $svc.StartType; '{#SERVICE.STATUS}'=$status_str})
    if ($worst -eq "Notfound" -or $statuses[$worst] -lt $statuses[$status_str]) {
        $worst = $status_str
    }
}

switch ($RTType) {
    "trapper" {
        '- {0}.overall {1}' -F $SGroupName, $worst
        $services.GetEnumerator()|ForEach-Object {'- "{0}.state[{1}]" {2}' -F $SGroupName, $_['{#SERVICE.NAME}'], $_['{#SERVICE.STATUS}']};
        break;
    }
    "item" {$worst; break;}
    "discovery" {@{'data'=$services}|ConvertTo-Json -Compress; break;}
}
