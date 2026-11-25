using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;

namespace Sp2Recomp.Launcher {
    public static class LauncherTests {
        static void Assert(bool condition, string message) { if (!condition) throw new Exception(message); }
        public static int Run(string fixtureExe, string report) {
            string root = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(report)), "fixture & spaced path");
            try {
                Directory.CreateDirectory(Path.Combine(root, "private", "analysis"));
                Directory.CreateDirectory(Path.Combine(root, "private", "extract", "romfs"));
                File.WriteAllText(Path.Combine(root, "private", "analysis", "main.bin"), "fixture");
                File.WriteAllText(Path.Combine(root, "SDL3.dll"), "fixture");
                File.Copy(fixtureExe, Path.Combine(root, "sp2-test.exe"), true);
                var settings = new Settings { GameDirectory = root, Executable = "sp2-test.exe" };
                Assert(Game.Validate(settings) == null, "Valid installation rejected");
                Assert(InputOptions.Codes(settings,"B")=="32" && InputOptions.Codes(settings,"ZL")=="16,90" && InputOptions.Codes(settings,"ZR")=="1,67", "Legacy settings lost current defaults");
                foreach(var invalid in new[]{"", "-1", "0,32", "1,1", "255", "256", "32,", "1,2,3,4,5", " 32"}) Assert(!InputOptions.Valid(invalid), "Invalid key accepted: "+invalid);
                InputOptions.Assign(settings,"B","71"); InputOptions.Assign(settings,"ZR","4"); InputOptions.Assign(settings,"STICK_R","86"); InputOptions.Assign(settings,"DPAD_UP","84");
                Assert(InputOptions.Display("1,67")=="Left mouse / C" && InputOptions.Display("0")=="Unassigned", "Key labels incorrect");
                new LauncherWindow(true).VerifyInputsUi();

                Environment.SetEnvironmentVariable("NX_PLAZA_60FPS", "1");
                Environment.SetEnvironmentVariable("NX_SYNC_CHUNKS", "0");
                Environment.SetEnvironmentVariable("NX_RING_CACHED", "0");
                Environment.SetEnvironmentVariable("NX_SUBMIT_CHUNK_DRAWS", "1");
                Environment.SetEnvironmentVariable("NX_HEADLESS", "1");
                Environment.SetEnvironmentVariable("NX_INPUT_SCRIPT", "unexpected");
                Environment.SetEnvironmentVariable("NX_BIND_B", "bad-inherited");
                var start = Game.StartInfo(settings);
                Assert(start.EnvironmentVariables["NX_BIND_B"]=="71" && start.EnvironmentVariables["NX_BIND_ZR"]=="4", "Saved bindings not passed to runtime");
                Assert(start.EnvironmentVariables["NX_RING_CACHED"] == "1", "Cached read-back memory not enabled");
                Assert(start.EnvironmentVariables["NX_PLAZA_60FPS"] == "0", "60 FPS was inherited");
                Assert(start.EnvironmentVariables["NX_SYNC_CHUNKS"] == "1" && start.EnvironmentVariables["NX_SUBMIT_CHUNK_DRAWS"] == "150", "Verified synchronous chunks were not retained");
                Assert(!start.EnvironmentVariables.ContainsKey("NX_HEADLESS") && !start.EnvironmentVariables.ContainsKey("NX_INPUT_SCRIPT"), "Diagnostics were inherited");
                Assert(start.EnvironmentVariables["NX_SWITCH_PRO"] == "1" && start.EnvironmentVariables["NX_MOUSE_GYRO"] == "0", "Controller defaults changed");
                Assert(start.UseShellExecute == false && start.WorkingDirectory == root, "Invalid process launch configuration");
                settings.SwitchPro = false; settings.FixedResolution = true; settings.Fullscreen = true;
                start = Game.StartInfo(settings);
                Assert(start.EnvironmentVariables["NX_SWITCH_PRO"] == "0" && start.EnvironmentVariables["NX_DISABLE_DYNAMIC_RESOLUTION"] == "1" && start.EnvironmentVariables["NX_FULLSCREEN"] == "1", "Options not applied");
                string config = Path.Combine(root, "settings.xml"), session = Path.Combine(root, "session.xml");
                Storage.Write(config, settings); Storage.Write(config, settings);
                var loaded = Storage.Read<Settings>(config);
                Assert(InputOptions.Codes(loaded,"B")=="71" && InputOptions.Codes(loaded,"STICK_R")=="86", "Binding settings round trip failed");
                Assert(loaded.GameDirectory == root && loaded.Fullscreen && loaded.MemoryGB == 13, "Settings round trip failed");
                settings.MemoryGB = 0; Assert(Game.Validate(settings) != null, "Invalid memory accepted"); settings.MemoryGB = 13;
                settings.Executable = "..\\sp2-test.exe"; Assert(Game.Validate(settings) != null, "Executable traversal accepted"); settings.Executable = "missing.exe";
                Assert(Game.Validate(settings) != null, "Missing executable accepted"); settings.Executable = "sp2-test.exe";
                Assert(Game.FindBuild(root) == "", "Diagnostic build automatically selected");
                File.Delete(Path.Combine(root, "private", "analysis", "main.bin"));
                Assert(Game.Validate(settings) != null, "Missing game image accepted");
                File.WriteAllText(Path.Combine(root, "private", "analysis", "main.bin"), "fixture");
                using (var runner = Game.StartRunner(config, session)) {
                    Session state = null;
                    for (int i = 0; i < 100; i++) {
                        Thread.Sleep(50);
                        try { state = Storage.Read<Session>(session); if (state.State == "Running") break; } catch (IOException) { }
                    }
                    Assert(state != null && state.State == "Running", "Detached game runner did not start");
                    Assert(Game.IsRunning(root), "Running game not detected");
                    string second = Path.Combine(root, "second-session.xml");
                    using (var duplicate = Game.StartRunner(config, second)) { Assert(duplicate.WaitForExit(10000), "Duplicate launch hung"); Assert(duplicate.ExitCode == 1, "Duplicate launch permitted"); }
                    Assert(Storage.Read<Session>(second).State == "Failed", "Duplicate launch not reported");
                    Assert(runner.WaitForExit(15000), "Output pipes deadlocked");
                    state = Storage.Read<Session>(session);
                    Assert(state.State == "Ended" && state.ExitCode == 7, "Exit status lost");
                    string log = File.ReadAllText(state.Log);
                    Assert(log.Contains("FIXTURE_STDOUT_END") && log.Contains("FIXTURE_STDERR_END") && log.Contains("Session ended | exit code 7"), "Log streams not fully drained");
                }
                string actual = File.ReadAllText(Path.Combine(root, "actual-environment.txt"));
                Assert(actual.Contains("NX_PLAZA_60FPS=0") && actual.Contains("NX_SWITCH_PRO=0") && actual.Contains("NX_FULLSCREEN=1") && actual.Contains("NX_DISABLE_DYNAMIC_RESOLUTION=1"), "Child environment differs from settings");
                Assert(actual.Contains("NX_RING_CACHED=1"), "Child did not receive cached read-back mode");
                Assert(actual.Contains("NX_SYNC_CHUNKS=1") && actual.Contains("NX_SUBMIT_CHUNK_DRAWS=150"), "Child did not receive verified chunk options");
                Assert(actual.Contains("NX_BIND_B=71") && actual.Contains("NX_BIND_ZR=4") && actual.Contains("NX_BIND_DPAD_UP=84"), "Child lost saved bindings");
                Assert(!actual.Contains("NX_HEADLESS") && !actual.Contains("NX_INPUT_SCRIPT"), "Child inherited automation");
                Assert(actual.Contains("CWD=" + root), "Spaced game folder mishandled");
                Assert(!Game.IsRunning(root), "Ended game still reported running");
                File.WriteAllText(report, "PASS: settings, validation, explicit defaults, option mapping, quoted paths, detached launch, duplicate launch guard, concurrent output drain, exit status, child environment, input capture/clear/reset, legacy defaults, binding persistence, embedded banner.\n");
                return 0;
            } catch (Exception e) { File.WriteAllText(report, "FAIL: " + e + "\n"); return 1; }
        }
    }
}
