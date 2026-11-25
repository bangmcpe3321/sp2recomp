param([Parameter(Mandatory=$true)][string]$Launcher, [string]$OutputDirectory = (Join-Path $PSScriptRoot '../../../build/launcher-tests'))
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$OutputDirectory = (Resolve-Path -LiteralPath $OutputDirectory).Path
$fixtureSource = Join-Path $OutputDirectory 'Fixture.cs'
@'
using System;
using System.Collections;
using System.IO;
using System.Text;
using System.Threading;
class Fixture {
    static int Main() {
        var data = new StringBuilder("CWD=" + Environment.CurrentDirectory + "\n");
        foreach (DictionaryEntry entry in Environment.GetEnvironmentVariables())
            if (((string)entry.Key).StartsWith("NX_")) data.Append(entry.Key + "=" + entry.Value + "\n");
        File.WriteAllText("actual-environment.txt", data.ToString());
        Thread.Sleep(2000);
        for (int i = 0; i < 5000; i++) { Console.WriteLine("OUT " + i + new string('o', 200)); Console.Error.WriteLine("ERR " + i + new string('e', 200)); }
        Console.WriteLine("FIXTURE_STDOUT_END"); Console.Error.WriteLine("FIXTURE_STDERR_END");
        return 7;
    }
}
'@ | Set-Content -LiteralPath $fixtureSource -Encoding UTF8
$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
$fixture = Join-Path $OutputDirectory 'Fixture.exe'
& $compiler /nologo /target:exe /platform:x64 "/out:$fixture" $fixtureSource
if ($LASTEXITCODE -ne 0) { throw 'Fixture compilation failed.' }
$report = Join-Path $OutputDirectory 'report.txt'
$test = Start-Process -FilePath (Resolve-Path -LiteralPath $Launcher).Path -ArgumentList @('--self-test', ('"' + $fixture + '"'), ('"' + $report + '"')) -PassThru -WindowStyle Hidden
if (!$test.WaitForExit(30000)) { throw 'Launcher regression timed out.' }
Get-Content -LiteralPath $report
if ($test.ExitCode -ne 0) { throw "Launcher regression failed: $($test.ExitCode)" }
