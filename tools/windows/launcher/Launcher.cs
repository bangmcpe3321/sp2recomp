using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Runtime.Serialization;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Markup;
using System.Windows.Input;
using System.Windows.Media.Imaging;
using System.Windows.Media;
using System.Windows.Threading;
using Forms = System.Windows.Forms;

namespace Sp2Recomp.Launcher {
    [DataContract]
    public sealed class Settings {
        [DataMember] public string GameDirectory = "";
        [DataMember] public string Executable = "";
        [DataMember] public bool SwitchPro = true;
        [DataMember] public bool MouseGyro = false;
        [DataMember] public bool FpsOverlay = true;
        [DataMember] public bool Fullscreen;
        [DataMember] public bool FixedResolution;
        [DataMember] public int MemoryGB = 13;
        [DataMember(EmitDefaultValue = false)] public List<InputMapping> InputMappings;
    }
    [DataContract]
    public sealed class Session {
        [DataMember] public string State = "Starting";
        [DataMember] public string GameDirectory;
        [DataMember] public string Executable;
        [DataMember] public string Log;
        [DataMember] public string Message;
        [DataMember] public int ProcessId;
        [DataMember] public int ExitCode;
    }
    public static class Storage {
        public static readonly string Root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "sp2recomp", "launcher");
        public static readonly string SettingsPath = Path.Combine(Root, "settings.xml");
        public static readonly string SessionPath = Path.Combine(Root, "last-session.xml");
        public static T Read<T>(string path) {
            using (var stream = File.OpenRead(path)) return (T)new DataContractSerializer(typeof(T)).ReadObject(stream);
        }
        public static void Write<T>(string path, T value) {
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path)));
            string temp = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
            try {
                using (var stream = File.Create(temp)) new DataContractSerializer(typeof(T)).WriteObject(stream, value);
                if (File.Exists(path)) File.Replace(temp, path, null); else File.Move(temp, path);
            } finally { if (File.Exists(temp)) File.Delete(temp); }
        }
    }
    public static class Game {
        public static readonly string[] Recommended = { "sp2-controller-gameplay.exe", "sp2-plaza-transition-safe.exe", "sp2.exe" };
        public static string FindBuild(string directory) {
            return Recommended.FirstOrDefault(name => File.Exists(Path.Combine(directory, name))) ?? "";
        }
        public static Settings Defaults(string preferredDirectory) {
            string folder = preferredDirectory;
            if (string.IsNullOrEmpty(folder) || !Directory.Exists(folder)) {
                folder = AppDomain.CurrentDomain.BaseDirectory;
                if (FindBuild(folder) == "") folder = Directory.Exists(@"C:\sp2stage\sp2win") ? @"C:\sp2stage\sp2win" : "";
            }
            return new Settings { GameDirectory = folder, Executable = FindBuild(folder) };
        }
        public static string Validate(Settings s) {
            if (string.IsNullOrWhiteSpace(s.GameDirectory) || !Directory.Exists(s.GameDirectory)) return "Choose your game folder in Settings.";
            if (string.IsNullOrWhiteSpace(s.Executable) || Path.GetFileName(s.Executable) != s.Executable || !s.Executable.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)) return "Choose a game executable in Settings.";
            string exe = Path.GetFullPath(Path.Combine(s.GameDirectory, s.Executable));
            if (string.Equals(exe, Program.Self, StringComparison.OrdinalIgnoreCase)) return "Choose the game executable, rather than the launcher.";
            if (!File.Exists(exe)) return "Game executable missing. Choose a build in Settings.";
            if (!File.Exists(Path.Combine(s.GameDirectory, "private", "analysis", "main.bin"))) return "Missing private\\analysis\\main.bin in the game folder.";
            if (!Directory.Exists(Path.Combine(s.GameDirectory, "private", "extract", "romfs"))) return "Missing private\\extract\\romfs in the game folder.";
            if (s.SwitchPro && !File.Exists(Path.Combine(s.GameDirectory, "SDL3.dll"))) return "SDL3.dll is missing. Install the controller runtime or switch off Switch Pro.";
            if (s.MemoryGB < 4 || s.MemoryGB > 32) return "Set a memory limit between 4 and 32 GB.";
            return null;
        }
        public static ProcessStartInfo StartInfo(Settings s) {
            var info = new ProcessStartInfo(Path.Combine(Path.GetFullPath(s.GameDirectory), s.Executable)) {
                WorkingDirectory = Path.GetFullPath(s.GameDirectory), UseShellExecute = false,
                CreateNoWindow = true, RedirectStandardError = true, RedirectStandardOutput = true
            };
            // Start every session from explicit settings, including when launched from a diagnostic shell.
            foreach (string key in info.EnvironmentVariables.Keys.Cast<string>().Where(k => k.StartsWith("NX_", StringComparison.OrdinalIgnoreCase)).ToArray()) info.EnvironmentVariables.Remove(key);
            info.EnvironmentVariables["NX_DATA_ROOT"] = "private";
            info.EnvironmentVariables["NX_MEM_LIMIT_GB"] = s.MemoryGB.ToString(CultureInfo.InvariantCulture);
            info.EnvironmentVariables["NX_GPU_TIMESTAMPS"] = "0";
            info.EnvironmentVariables["NX_RING_CACHED"] = "1";
            info.EnvironmentVariables["NX_SYNC_CHUNKS"] = "1";
            info.EnvironmentVariables["NX_SUBMIT_CHUNK_DRAWS"] = "150";
            info.EnvironmentVariables["NX_PLAZA_60FPS"] = "0";
            info.EnvironmentVariables["NX_SIXAXIS"] = "1";
            info.EnvironmentVariables["NX_SWITCH_PRO"] = s.SwitchPro ? "1" : "0";
            info.EnvironmentVariables["NX_MOUSE_GYRO"] = s.MouseGyro ? "1" : "0";
            info.EnvironmentVariables["NX_FPS_OVERLAY"] = s.FpsOverlay ? "1" : "0";
            info.EnvironmentVariables["NX_FULLSCREEN"] = s.Fullscreen ? "1" : "0";
            info.EnvironmentVariables["NX_DISABLE_DYNAMIC_RESOLUTION"] = s.FixedResolution ? "1" : "0";
            foreach (var action in InputOptions.All) info.EnvironmentVariables["NX_BIND_" + action.Action] = InputOptions.Codes(s, action.Action);
            return info;
        }
        public static bool IsRunning(string directory) {
            if (string.IsNullOrEmpty(directory)) return false;
            string full;
            try { full = Path.GetFullPath(directory).TrimEnd(Path.DirectorySeparatorChar); } catch { return false; }
            foreach (var process in Process.GetProcesses()) {
                using (process) {
                    try {
                        if (!process.ProcessName.StartsWith("sp2", StringComparison.OrdinalIgnoreCase) || process.ProcessName.StartsWith("sp2recomp-Launcher", StringComparison.OrdinalIgnoreCase)) continue;
                        if (string.Equals(Path.GetDirectoryName(process.MainModule.FileName).TrimEnd(Path.DirectorySeparatorChar), full, StringComparison.OrdinalIgnoreCase)) return true;
                    } catch (System.ComponentModel.Win32Exception) { } catch (InvalidOperationException) { }
                }
            }
            return false;
        }
        public static string LockName(string directory) {
            using (var hash = SHA256.Create()) return @"Local\sp2recomp.Game." + BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(Path.GetFullPath(directory).TrimEnd('\\').ToUpperInvariant()))).Replace("-", "");
        }
        // Windows argv quoting, including trailing backslashes in directory paths.
        public static string Quote(string value) {
            var result = new StringBuilder("\""); int slashes = 0;
            foreach (char ch in value) {
                if (ch == '\\') { slashes++; continue; }
                result.Append('\\', ch == '"' ? slashes * 2 + 1 : slashes); slashes = 0; result.Append(ch);
            }
            return result.Append('\\', slashes * 2).Append('"').ToString();
        }
        public static Process StartRunner(string settings, string session) {
            return Process.Start(new ProcessStartInfo(Program.Self, "--run-session " + Quote(settings) + " " + Quote(session)) { UseShellExecute = false, CreateNoWindow = true });
        }
        public static int RunSession(string settingsPath, string sessionPath) {
            var state = new Session();
            try {
                var settings = Storage.Read<Settings>(settingsPath);
                state.GameDirectory = settings.GameDirectory; state.Executable = settings.Executable;
                string problem = Validate(settings); if (problem != null) throw new InvalidOperationException(problem);
                using (var gate = new Mutex(false, LockName(settings.GameDirectory))) {
                    bool owns;
                    try { owns = gate.WaitOne(0); } catch (AbandonedMutexException) { owns = true; }
                    if (!owns) throw new InvalidOperationException("A game is already running from this folder.");
                    try {
                        if (IsRunning(settings.GameDirectory)) throw new InvalidOperationException("A game is already running from this folder.");
                        string logs = Path.Combine(Path.GetDirectoryName(sessionPath), "logs"); Directory.CreateDirectory(logs);
                        state.Log = Path.Combine(logs, "session-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + "-" + Guid.NewGuid().ToString("N").Substring(0, 6) + ".log");
                        using (var log = new StreamWriter(state.Log, false, Encoding.UTF8)) {
                            log.AutoFlush = true; object sync = new object();
                            log.WriteLine("sp2recomp launcher | " + DateTime.Now.ToString("O"));
                            log.WriteLine("Build: " + settings.Executable + " | original game timing");
                            using (var process = new Process { StartInfo = StartInfo(settings) }) {
                                process.OutputDataReceived += delegate(object sender, DataReceivedEventArgs e) { if (e.Data != null) lock (sync) log.WriteLine(e.Data); };
                                process.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e) { if (e.Data != null) lock (sync) log.WriteLine(e.Data); };
                                process.Start(); state.ProcessId = process.Id; state.State = "Running"; Storage.Write(sessionPath, state);
                                process.BeginOutputReadLine(); process.BeginErrorReadLine(); process.WaitForExit();
                                state.ExitCode = process.ExitCode;
                                log.WriteLine("Session ended | exit code " + state.ExitCode);
                            }
                        }
                        state.State = "Ended"; Storage.Write(sessionPath, state); return 0;
                    } finally { gate.ReleaseMutex(); }
                }
            } catch (Exception e) {
                state.State = "Failed"; state.Message = e.Message;
                try { Storage.Write(sessionPath, state); } catch { }
                return 1;
            }
        }
    }
    public sealed class LauncherWindow {
        readonly Window window;
        readonly DispatcherTimer timer = new DispatcherTimer();
        Settings settings;
        readonly bool previewMode;
        readonly Dictionary<string, Button> bindingButtons = new Dictionary<string, Button>();
        InputDefinition recording;
        bool loading;
        bool pending;
        DateTime launchTime;
        string persistenceError;
        string sessionPath = Storage.SessionPath;
        T Control<T>(string name) where T : FrameworkElement { return (T)window.FindName(name); }
        public LauncherWindow() : this(false) {}
        internal LauncherWindow(bool preview) {
            previewMode = preview;
            using (var resource = typeof(Program).Assembly.GetManifestResourceStream("MainWindow.xaml")) window = (Window)XamlReader.Load(resource);
            using (var icon = typeof(Program).Assembly.GetManifestResourceStream("LauncherIcon.png")) {
                if (icon == null) throw new InvalidOperationException("Launcher icon is missing.");
                window.Icon = BitmapFrame.Create(icon, BitmapCreateOptions.PreservePixelFormat, BitmapCacheOption.OnLoad);
                window.Icon.Freeze();
            }
            window.Width = Math.Min(window.Width, SystemParameters.WorkArea.Width - 40);
            window.Height = Math.Min(window.Height, SystemParameters.WorkArea.Height - 40);
            window.MinWidth = Math.Min(window.MinWidth, window.Width); window.MinHeight = Math.Min(window.MinHeight, window.Height);
            try { settings = preview ? Game.Defaults(null) : Storage.Read<Settings>(Storage.SettingsPath); if (settings == null) throw new SerializationException(); }
            catch (Exception) { settings = Game.Defaults(null); }
            LoadArtwork(); BuildInputs(); Bind();
            window.PreviewKeyDown += delegate(object sender, KeyEventArgs e) {
                if (recording == null) return;
                e.Handled = true;
                Key pressed = e.Key == Key.System ? e.SystemKey : e.Key;
                if (pressed == Key.Escape) { CancelRecording(); return; }
                CaptureBinding(InputOptions.Normalize(KeyInterop.VirtualKeyFromKey(pressed)));
            };
            window.PreviewMouseDown += delegate(object sender, MouseButtonEventArgs e) {
                if (recording == null) return;
                e.Handled = true;
                int code = e.ChangedButton == MouseButton.Left ? 1 : e.ChangedButton == MouseButton.Right ? 2 : e.ChangedButton == MouseButton.Middle ? 4 : e.ChangedButton == MouseButton.XButton1 ? 5 : 6;
                CaptureBinding(code);
            };
            Control<Button>("InputsNav").Click += delegate { Page("Inputs"); };
            Control<Button>("ResetInputsControl").Click += delegate { CancelRecording(); settings.InputMappings = null; InputOptions.Ensure(settings); RefreshBindings(); Save(); Control<TextBlock>("BindingStatus").Text = "Input defaults restored."; };
            Control<Button>("HomeNav").Click += delegate { Page("Home"); };
            Control<Button>("SettingsNav").Click += delegate { Page("Settings"); };
            Control<Button>("AboutNav").Click += delegate { Page("About"); };
            Control<Button>("BrowseFolder").Click += delegate {
                using (var dialog = new Forms.FolderBrowserDialog { Description = "Choose the folder containing the game executable and private data", SelectedPath = settings.GameDirectory }) {
                    if (dialog.ShowDialog() != Forms.DialogResult.OK) return;
                    settings.GameDirectory = dialog.SelectedPath; settings.Executable = Game.FindBuild(dialog.SelectedPath); Bind(); Save(); Refresh();
                }
            };
            Control<Button>("BrowseExe").Click += delegate {
                var dialog = new Microsoft.Win32.OpenFileDialog { Title = "Choose the game executable", Filter = "Game executable (*.exe)|*.exe", InitialDirectory = settings.GameDirectory };
                if (dialog.ShowDialog(window) != true) return;
                settings.GameDirectory = Path.GetDirectoryName(dialog.FileName); settings.Executable = Path.GetFileName(dialog.FileName); Bind(); Save(); Refresh();
            };
            foreach (string name in new[] { "ProControl", "MouseControl", "FpsControl", "FullscreenControl", "FixedControl" }) {
                Control<CheckBox>(name).Checked += Changed; Control<CheckBox>(name).Unchecked += Changed;
            }
            foreach (string name in new[] { "FolderControl", "ExeControl", "MemoryControl" }) Control<TextBox>(name).TextChanged += Changed;
            Control<Button>("ResetControl").Click += delegate { settings = Game.Defaults(settings.GameDirectory); Bind(); Save(); Refresh(); };
            Control<Button>("OpenFolderControl").Click += delegate { Open(settings.GameDirectory); };
            Control<Button>("OpenLogControl").Click += delegate { string logs = Path.Combine(Storage.Root, "logs"); Directory.CreateDirectory(logs); Open(logs); };
            Control<Button>("RepoControl").Click += delegate { Open("https://github.com/bangmcpe3321/sp2recomp"); };
            Control<Button>("PlayControl").Click += Play;
            window.Closing += delegate { Save(); }; // The independent session runner continues logging after the GUI closes.
            timer.Interval = TimeSpan.FromSeconds(2); timer.Tick += delegate { Refresh(); }; if (!preview) timer.Start(); Refresh();
        }
        void Bind() {
            loading = true;
            Control<TextBox>("FolderControl").Text = settings.GameDirectory;
            Control<TextBox>("ExeControl").Text = settings.Executable;
            Control<TextBox>("MemoryControl").Text = settings.MemoryGB.ToString(CultureInfo.InvariantCulture);
            Control<CheckBox>("ProControl").IsChecked = settings.SwitchPro;
            Control<CheckBox>("MouseControl").IsChecked = settings.MouseGyro;
            Control<CheckBox>("FpsControl").IsChecked = settings.FpsOverlay;
            Control<CheckBox>("FullscreenControl").IsChecked = settings.Fullscreen;
            Control<CheckBox>("FixedControl").IsChecked = settings.FixedResolution;
            RefreshBindings();
            loading = false;
        }
        void Changed(object sender, RoutedEventArgs args) {
            if (loading) return;
            settings.GameDirectory = Control<TextBox>("FolderControl").Text.Trim();
            settings.Executable = Control<TextBox>("ExeControl").Text.Trim();
            int memory; settings.MemoryGB = int.TryParse(Control<TextBox>("MemoryControl").Text, out memory) ? memory : 0;
            settings.SwitchPro = Control<CheckBox>("ProControl").IsChecked == true;
            settings.MouseGyro = Control<CheckBox>("MouseControl").IsChecked == true;
            settings.FpsOverlay = Control<CheckBox>("FpsControl").IsChecked == true;
            settings.Fullscreen = Control<CheckBox>("FullscreenControl").IsChecked == true;
            settings.FixedResolution = Control<CheckBox>("FixedControl").IsChecked == true;
            Save(); Refresh();
        }
        bool Save() {
            if (previewMode) return true;
            try { Storage.Write(Storage.SettingsPath, settings); persistenceError = null; return true; }
            catch (Exception e) { persistenceError = "Could not save settings: " + e.Message; return false; }
        }
        void Page(string name) {
            CancelRecording();
            foreach (string page in new[] { "Home", "Settings", "Inputs", "About" }) {
                Control<StackPanel>(page + "Page").Visibility = name == page ? Visibility.Visible : Visibility.Collapsed;
                Control<Button>(page + "Nav").Background = (Brush)new BrushConverter().ConvertFromString(name == page ? "#47325F" : "Transparent");
            }
            Control<ScrollViewer>("ContentScroll").ScrollToTop();
        }
        void LoadArtwork() {
            using (var resource = typeof(Program).Assembly.GetManifestResourceStream("SessionArt.png")) {
                if (resource == null) throw new InvalidOperationException("Launcher artwork is missing.");
                var image = new BitmapImage(); image.BeginInit(); image.CacheOption = BitmapCacheOption.OnLoad; image.StreamSource = resource; image.EndInit(); image.Freeze();
                var cropped = new CroppedBitmap(image, new Int32Rect(0, image.PixelHeight * 399 / 1080, image.PixelWidth, image.PixelHeight * 427 / 1080)); cropped.Freeze();
                Control<Border>("HeroArtwork").Background = new ImageBrush(cropped) { Stretch = Stretch.UniformToFill, AlignmentX = AlignmentX.Center, AlignmentY = AlignmentY.Center };
            }
        }
        void BuildInputs() {
            string group = null;
            foreach (var definition in InputOptions.All) {
                var action = definition;
                if (group != action.Group) {
                    group = action.Group;
                    Control<StackPanel>("BindingRows").Children.Add(new TextBlock { Text = group.ToUpperInvariant(), FontSize = 11, FontWeight = FontWeights.Bold, Foreground = (Brush)new BrushConverter().ConvertFromString("#ACA6BC"), Margin = new Thickness(0,18,0,8) });
                }
                var row = new Grid { Margin = new Thickness(0,0,0,8) };
                row.ColumnDefinitions.Add(new ColumnDefinition()); row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(185) }); row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(66) });
                row.Children.Add(new TextBlock { Text = action.Label, VerticalAlignment = VerticalAlignment.Center, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0,0,12,0) });
                var assign = new Button { Padding = new Thickness(12,10,12,10), ToolTip = "Assign a key or mouse button" }; System.Windows.Automation.AutomationProperties.SetName(assign,"Bind " + action.Label); Grid.SetColumn(assign,1); row.Children.Add(assign); bindingButtons[action.Action] = assign;
                assign.Click += delegate { CancelRecording(); recording = action; assign.Content = "Press a key…"; Control<TextBlock>("BindingStatus").Text = "Recording " + action.Label + ". Press a key or mouse button; Esc cancels."; };
                var clear = new Button { Tag = action.Action, Content = "Clear", Padding = new Thickness(8,10,8,10), FontSize = 11, Margin = new Thickness(8,0,0,0) }; System.Windows.Automation.AutomationProperties.SetName(clear,"Clear " + action.Label); Grid.SetColumn(clear,2); row.Children.Add(clear);
                clear.Click += delegate { CancelRecording(); InputOptions.Assign(settings,action.Action,"0"); RefreshBindings(); Save(); Control<TextBlock>("BindingStatus").Text = action.Label + " is unassigned."; };
                Control<StackPanel>("BindingRows").Children.Add(row);
            }
        }
        void RefreshBindings() {
            foreach (var action in InputOptions.All) bindingButtons[action.Action].Content = InputOptions.Display(InputOptions.Codes(settings,action.Action));
        }
        void CancelRecording() { recording = null; RefreshBindings(); Control<TextBlock>("BindingStatus").Text = "Select a binding to change it."; }
        void CaptureBinding(int code) {
            if (recording == null) return;
            if (code < 1 || code > 254 || InputOptions.Reserved(code)) { Control<TextBlock>("BindingStatus").Text = "F1, F3 and F11 are launcher shortcuts. Choose another key, or Esc to cancel."; return; }
            var action = recording; recording = null;
            InputOptions.Assign(settings,action.Action,code.ToString(CultureInfo.InvariantCulture)); RefreshBindings(); Save();
            var duplicates = InputOptions.All.Where(d=>d.Action!=action.Action && InputOptions.Codes(settings,d.Action).Split(',').Contains(code.ToString(CultureInfo.InvariantCulture))).Select(d=>d.Label).ToArray();
            Control<TextBlock>("BindingStatus").Text = action.Label + " → " + InputOptions.KeyName(code) + (duplicates.Length == 0 ? ". Saved for the next session." : ". Also used by " + string.Join(", ",duplicates) + ".");
        }
        internal void VerifyInputsUi() {
            if(!previewMode)throw new InvalidOperationException("UI checks require preview mode.");
            Page("Inputs");
            bindingButtons["B"].RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            if(recording==null)throw new Exception("Binding record button did not activate.");
            CaptureBinding(112); if(recording==null)throw new Exception("Reserved host key accepted.");
            CaptureBinding(71); if(InputOptions.Codes(settings,"B")!="71" || recording!=null)throw new Exception("Captured key not applied.");
            bindingButtons["ZR"].RaiseEvent(new RoutedEventArgs(Button.ClickEvent)); CaptureBinding(4);
            if(InputOptions.Codes(settings,"ZR")!="4")throw new Exception("Mouse binding not applied.");
            var clear=Control<StackPanel>("BindingRows").Children.OfType<Grid>().SelectMany(g=>g.Children.OfType<Button>()).First(b=>(string)b.Tag=="B");
            clear.RaiseEvent(new RoutedEventArgs(Button.ClickEvent)); if(InputOptions.Codes(settings,"B")!="0")throw new Exception("Clear binding failed.");
            bindingButtons["X"].RaiseEvent(new RoutedEventArgs(Button.ClickEvent)); CancelRecording();
            if(InputOptions.Codes(settings,"X")!="74" || recording!=null)throw new Exception("Cancel changed binding.");
            Control<Button>("ResetInputsControl").RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            if(InputOptions.Codes(settings,"B")!="32" || InputOptions.Codes(settings,"ZR")!="1,67")throw new Exception("Restore defaults failed.");
            var brush=Control<Border>("HeroArtwork").Background as ImageBrush;
            if(brush==null || ((BitmapSource)brush.ImageSource).PixelHeight!=427)throw new Exception("Embedded artwork crop missing.");
        }
        internal void RenderPreview(string directory) {
            Directory.CreateDirectory(directory);
            foreach (string page in new[] { "Home", "Inputs", "InputsActions" }) {
                // A fresh visual tree per image avoids stale offscreen render caches.
                var view = new LauncherWindow(true);
                view.Page(page == "InputsActions" ? "Inputs" : page);
                var visual = (FrameworkElement)view.window.Content;
                visual.Measure(new Size(1000,740)); visual.Arrange(new Rect(0,0,1000,740)); visual.UpdateLayout();
                if(page == "InputsActions") { view.Control<ScrollViewer>("ContentScroll").ScrollToVerticalOffset(480); visual.UpdateLayout(); }
                var bitmap = new RenderTargetBitmap(1000,740,96,96,PixelFormats.Pbgra32); bitmap.Render(visual);
                var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
                using(var output=File.Create(Path.Combine(directory,page.ToLowerInvariant()+".png"))) encoder.Save(output);
            }
        }
        void Open(string path) {
            try { if (!string.IsNullOrEmpty(path)) Process.Start(new ProcessStartInfo(path) { UseShellExecute = true }); }
            catch (Exception e) { MessageBox.Show(window, e.Message, "Could not open", MessageBoxButton.OK, MessageBoxImage.Information); }
        }
        void Play(object sender, RoutedEventArgs args) {
            string problem = Game.Validate(settings);
            if (problem != null) { Page("Settings"); Refresh(); return; }
            if (pending || Game.IsRunning(settings.GameDirectory)) { Refresh(); return; }
            if (!Save()) { Refresh(); return; }
            try {
                sessionPath = Path.Combine(Storage.Root, "session-" + Guid.NewGuid().ToString("N") + ".xml");
                string snapshot = sessionPath + ".settings.xml";
                Storage.Write(snapshot, settings);
                Storage.Write(Storage.SessionPath, new Session { State = "Starting", Message = sessionPath });
                using (var runner = Game.StartRunner(snapshot, sessionPath)) { }
                pending = true; launchTime = DateTime.UtcNow; Refresh();
            } catch (Exception e) { MessageBox.Show(window, e.Message, "Could not launch", MessageBoxButton.OK, MessageBoxImage.Information); }
        }
        void Refresh() {
            var play = Control<Button>("PlayControl");
            string message = null;
            bool running = Game.IsRunning(settings.GameDirectory);
            try {
                if (sessionPath == Storage.SessionPath && File.Exists(sessionPath)) {
                    var pointer = Storage.Read<Session>(sessionPath);
                    if (pointer.State == "Starting" && !string.IsNullOrEmpty(pointer.Message)) sessionPath = pointer.Message;
                }
                if (File.Exists(sessionPath)) {
                    var session = Storage.Read<Session>(sessionPath);
                    if (string.Equals(session.GameDirectory, settings.GameDirectory, StringComparison.OrdinalIgnoreCase)) {
                        if (session.State != "Starting") pending = false;
                        if (session.State == "Failed") message = session.Message;
                        if (session.State == "Ended") message = session.ExitCode == 0 ? "Session ended. Ready when you are." : "Game closed (exit code " + session.ExitCode + "). See launch logs.";
                    }
                }
            } catch (IOException) { } catch (SerializationException) { } catch (System.Xml.XmlException) { } catch (UnauthorizedAccessException) { }
            if (pending && DateTime.UtcNow - launchTime > TimeSpan.FromSeconds(20)) { pending = false; message = "Launch did not finish starting. See launch logs."; }
            string problem;
            try { problem = Game.Validate(settings); } catch (Exception) { problem = "Check the game folder and executable in Settings."; }
            Control<TextBlock>("StatusControl").Text = running ? "Game is running. Enjoy your session." : pending ? "Starting your game…" : persistenceError ?? problem ?? message ?? "Ready to play.";
            play.Content = running ? "RUNNING" : pending ? "STARTING" : "PLAY  ▶";
            play.IsEnabled = !running && !pending;
            Control<TextBlock>("GameSummary").Text = string.IsNullOrEmpty(settings.Executable) ? "Choose your game folder in Settings to get started." : "Selected build  ·  " + settings.Executable;
        }
        public void Show() { new Application().Run(window); }
    }
    public static class Program {
        public static readonly string Self = typeof(Program).Assembly.Location;
        [STAThread]
        public static int Main(string[] args) {
            if (args.Length == 2 && args[0] == "--render-preview") { new LauncherWindow(true).RenderPreview(args[1]); return 0; }
            if (args.Length == 3 && args[0] == "--run-session") return Game.RunSession(args[1], args[2]);
            if (args.Length == 3 && args[0] == "--self-test") return LauncherTests.Run(args[1], args[2]);
            try { new LauncherWindow().Show(); return 0; }
            catch (Exception e) { MessageBox.Show(e.Message, "sp2recomp Launcher", MessageBoxButton.OK, MessageBoxImage.Error); return 1; }
        }
    }
}
