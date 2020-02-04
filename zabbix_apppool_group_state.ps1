param(
    [Parameter(Mandatory=$true, HelpMessage="App pool group's name", ParameterSetName="Normal")]
    [string]
    $PGroupName,
    [Parameter(HelpMessage="App pool name regex", ParameterSetName="Normal")]
    [string]
    $PNameRegex,
    [Parameter(HelpMessage="App pools names list", ParameterSetName="Normal")]
    [string]
    $PNameList,
    [Parameter(HelpMessage="File with app pools names list", ParameterSetName="Normal")]
    [string]
    $PNameListFile,
    [Parameter(HelpMessage="Type of info to be returned", ParameterSetName="Normal")]
    [ValidateSet("item", "trapper", "discovery")]
    [string]
    $RTType="trapper",
    [Parameter(HelpMessage="Get script's version", ParameterSetName="Version")]
    [switch]
    [Alias("v")]
    $version
)

$_FILE_VER = "to_be_filled_by_CI"
if ($version) {
    $_FILE_VER
    exit
}

$states = @(
    "Started",
    "Starting",
    "Stopping",
    "Stopped",
    "Unknown"
)
$states_h = @{}
$i = 0
foreach ($state in $states) {
    $states_h[$state] = $i++
}
$states = $states_h

Import-Module WebAdministration

if ($PSBoundParameters.ContainsKey("PNameRegex")) {
    $poolnames = @((Get-ChildItem IIS:\AppPools | Where-Object {$_.Name -imatch $PNameRegex}).Name)
}
else {
    $poolnames = @()
}
if ($PSBoundParameters.ContainsKey("PNameList")) {
    $poolnames += @($SNameList)
}
if ($PSBoundParameters.ContainsKey("PNameListFile")) {
    $svcnames += @(Get-Content $PNameListFile)
}

$worst = "Notfound"
$pools = [System.Collections.ArrayList] @()
foreach ($pool in $(Get-ChildItem IIS:\AppPools|Where-Object {$_.Name -in $poolnames})) {
    $state_str = [string] $pool.State
    [void] $pools.Add(@{'{#POOL.NAME}'=$pool.Name; '{#POOL.STATE}'=$state_str})
    if ($worst -eq "Notfound" -or $states[$worst] -lt $states[$state_str]) {
        $worst = $state_str
    }
}

switch ($RTType) {
    "trapper" {
        '- {0}.overall {1}' -F $PGroupName, $worst
        $pools.GetEnumerator()|ForEach-Object {'- "{0}.state[{1}]" {2}' -F $PGroupName, $_['{#POOL.NAME}'], $_['{#POOL.STATE}']};
        break;
    }
    "item" {$worst; break;}
    "discovery" {@{'data'=$pools}|ConvertTo-Json -Compress; break;}
}
