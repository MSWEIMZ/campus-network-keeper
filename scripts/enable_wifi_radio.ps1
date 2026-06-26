Add-Type -AssemblyName System.Runtime.WindowsRuntime

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

$asTaskAction = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction' })[0]
function AwaitAction($WinRtTask) {
    $netTask = $asTaskAction.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
}

$radioType = [Windows.Devices.Radios.Radio, Windows.Devices.Radios, ContentType = WindowsRuntime]
$radios = Await ($radioType::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])

foreach ($radio in $radios) {
    $stateVal = [int]$radio.State
    $kindVal = [int]$radio.Kind
    Write-Host "Name: $($radio.Name)"
    Write-Host "  Kind value: $kindVal (expected WiFi=2)"
    Write-Host "  State value: $stateVal (expected Off=0, On=1)"
    Write-Host "  ToString: $($radio.State)"
    
    # 无论什么值都尝试开启
    Write-Host "  -> Attempting SetStateAsync(On)..."
    try {
        AwaitAction ($radio.SetStateAsync([Windows.Devices.Radios.RadioState]::On))
        $newState = [int]$radio.State
        Write-Host "  -> SUCCESS! New state value: $newState ($($radio.State))"
    } catch {
        Write-Host "  -> FAILED: $($_.Exception.Message)"
    }
}
