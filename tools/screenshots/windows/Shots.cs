using System.Collections.ObjectModel;
using System.IO;
using System.Reflection;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Markup;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using ProxmoxSpiceManager.Models;
using ProxmoxSpiceManager.Services;

namespace ProxmoxSpiceManager.Shots;

// Drives the real MainWindow with mock data (nothing touches a network) and saves PNGs of it.
// Usage: Shots.exe <output folder>
static class Program
{
    const BindingFlags F = BindingFlags.Instance | BindingFlags.NonPublic;

    static T Get<T>(object o, string name) =>
        (T)(o.GetType().GetField(name, F) ?? throw new MissingFieldException(o.GetType().Name, name)).GetValue(o)!;

    static void Call(object o, string name, params object?[] args) =>
        (o.GetType().GetMethod(name, F) ?? throw new MissingMethodException(o.GetType().Name, name)).Invoke(o, args);

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    static extern bool SetCursorPos(int x, int y);

    static string _log = "shots.log";
    static void Log(string m) => File.AppendAllText(_log, $"{DateTime.Now:HH:mm:ss.fff} {m}\n");

    [STAThread]
    static int Main(string[] args)
    {
        var outDir = args.Length > 0 ? args[0] : ".";
        _log = Path.Combine(outDir, "shots.log");
        Log("starting");
        AppDomain.CurrentDomain.UnhandledException += (_, e) => { Log($"unhandled: {e.ExceptionObject}"); Environment.Exit(3); };
        App app;
        MainWindow window;
        try
        {
            app = new App();
            Log("app created");
            app.InitializeComponent();
            // App.xaml's StartupUri would open a second MainWindow; the setter refuses null
            (typeof(Application).GetField("_startupUri", F) ?? throw new MissingFieldException("Application", "_startupUri"))
                .SetValue(app, null);
            // Wine has no visual styles, so WPF would fall back to its Classic look; use the
            // Aero2 theme Windows 10 and 11 give stock controls
            app.Resources.MergedDictionaries.Add(new ResourceDictionary
            {
                Source = new Uri("/PresentationFramework.Aero2;component/themes/aero2.normalcolor.xaml", UriKind.Relative),
            });
            ApplyAppearance("Catppuccin Mocha", "Orange");
            Log("theme applied");
            window = CreateWindow();
            Log("window created");
        }
        catch (Exception ex)
        {
            Log($"setup failed: {ex}");
            return 2;
        }
        var exitCode = 0;
        var started = false;
        window.ContentRendered += (_, _) =>
        {
            // Swapping in the prototypes re-raises ContentRendered; capture once
            if (started) return;
            started = true;
            Log("rendered");
            // Park the pointer outside the window so nothing is captured mid-hover
            SetCursorPos(1270, 1000);
            try
            {
                Populate(window);
                Capture(window, Path.Combine(outDir, "windows-main.png"));
                foreach (var theme in Themes.All.Keys)
                {
                    ApplyAppearance(theme, Themes.DefaultAccent);
                    Call(window, "RefreshClusterList");
                    Pump(400);
                    Capture(window, Path.Combine(outDir, $"windows-main-{Slug(theme)}.png"));
                }
                ApplyAppearance("Catppuccin Mocha", Themes.DefaultAccent);
                Call(window, "RefreshClusterList");
                CaptureStates(window, outDir);
                CaptureAddCluster(window, outDir);
                if (args.Length > 1)
                    CaptureProposals(window, args[1], outDir);
            }
            catch (Exception ex)
            {
                Log($"capture failed: {ex}");
                exitCode = 1;
            }
            app.Shutdown(exitCode);
        };
        Log("running");
        app.Run(window);
        return exitCode;
    }

    // Search, filter chips and multi-select, driven through the real controls
    static void CaptureStates(MainWindow w, string outDir)
    {
        var list = (ListBox)w.FindName("VmList");
        var search = (TextBox)w.FindName("SearchBox");
        var running = (RadioButton)w.FindName("FilterRunning");
        var all = (RadioButton)w.FindName("FilterAll");

        list.SelectedItems.Clear();
        foreach (var vm in list.Items.OfType<VmDisplayItem>().Where(v => v.VmId is 101 or 103 or 130))
            list.SelectedItems.Add(vm);
        Pump(400);
        Capture(w, Path.Combine(outDir, "windows-state-multiselect.png"));

        search.Text = "win";
        Pump(400);
        Capture(w, Path.Combine(outDir, "windows-state-search.png"));
        search.Text = "";

        running.IsChecked = true;
        Pump(400);
        Capture(w, Path.Combine(outDir, "windows-state-running.png"));
        all.IsChecked = true;

        search.Text = "nothing-matches";
        Pump(400);
        Capture(w, Path.Combine(outDir, "windows-state-empty.png"));
        search.Text = "";

        var config = Get<AppConfig>(w, "_config");
        var group = (System.Windows.Controls.Primitives.ToggleButton)w.FindName("GroupToggle");
        config.GroupByNode = false;
        config.VmSort = "ip";
        group.IsChecked = false;
        Call(w, "ApplySortAndGrouping");
        Pump(400);
        Capture(w, Path.Combine(outDir, "windows-state-ungrouped.png"));

        // A VM with Notes in Proxmox: its first line in the list, all of it in the inspector
        list.SelectedItems.Clear();
        list.SelectedItem = list.Items.OfType<VmDisplayItem>().First(v => v.VmId == 102);
        Pump(400);
        Capture(w, Path.Combine(outDir, "windows-state-proxmox-notes.png"));

        // Wide window with IPv6 on: the address column grows to show every address
        Call(w, "ToggleIpv6");
        w.Width = 1800;
        Pump(600);
        Capture(w, Path.Combine(outDir, "windows-state-wide.png"));
        w.Width = 1280;
        Call(w, "ToggleIpv6");
        Pump(400);
        config.GroupByNode = true;
        config.VmSort = "vmid";
        group.IsChecked = true;
        Call(w, "ApplySortAndGrouping");

        // Regrouping rebuilds the headings, which read their folded state back
        var collapsed = Get<HashSet<string>>(w, "_collapsedNodes");
        collapsed.Add("pve3");
        Call(w, "ApplySortAndGrouping");
        Pump(400);
        Capture(w, Path.Combine(outDir, "windows-state-collapsed.png"));
        collapsed.Clear();
        Call(w, "ApplySortAndGrouping");
        Log("states captured");
    }

    // First-run setup: the Add Cluster dialog, filled in, not modal so capturing can go on
    static void CaptureAddCluster(MainWindow w, string outDir)
    {
        var dialog = new ProxmoxSpiceManager.Dialogs.ClusterDialog(Get<AppConfig>(w, "_config")) { Owner = w };
        ((TextBox)dialog.FindName("NameBox")).Text = "Homelab";
        ((TextBox)dialog.FindName("HostBox")).Text = "https://pve1.example.com:8006";
        ((TextBox)dialog.FindName("TokenIdBox")).Text = "spice@pve!spice-manager";
        ((PasswordBox)dialog.FindName("TokenSecretBox")).Password = "00000000-0000-0000-0000-000000000000";
        dialog.Show();
        Pump(600);
        Capture(dialog, Path.Combine(outDir, "windows-add-cluster.png"));
        dialog.Close();

        // The same with a Proxmox user and password, and the prompt that asks for the password
        dialog = new ProxmoxSpiceManager.Dialogs.ClusterDialog(Get<AppConfig>(w, "_config")) { Owner = w };
        ((TextBox)dialog.FindName("NameBox")).Text = "Homelab";
        ((TextBox)dialog.FindName("HostBox")).Text = "https://pve1.example.com:8006";
        ((RadioButton)dialog.FindName("PasswordRadio")).IsChecked = true;
        ((TextBox)dialog.FindName("UsernameBox")).Text = "spice@pve";
        dialog.Show();
        Pump(600);
        Capture(dialog, Path.Combine(outDir, "windows-add-cluster-password.png"));
        dialog.Close();

        var prompt = new ProxmoxSpiceManager.Dialogs.PasswordDialog("spice@pve", "https://pve1.example.com:8006") { Owner = w };
        ((PasswordBox)prompt.FindName("PasswordBox")).Password = "example-password";
        prompt.Show();
        Pump(600);
        Capture(prompt, Path.Combine(outDir, "windows-password-prompt.png"));
        prompt.Close();
        Log("add cluster captured");
    }

    static MainWindow CreateWindow() => new()
    {
        Width = 1280, Height = 760,
        WindowStartupLocation = WindowStartupLocation.Manual, Left = 0, Top = 0,
    };

    static void Populate(MainWindow w)
    {
        var config = Get<AppConfig>(w, "_config");
        config.Clusters.Clear();
        foreach (var name in new[] { "Homelab", "Lab East", "DR Site" })
            config.Clusters.Add(new ClusterConfig { Name = name, Host = $"https://{name.ToLowerInvariant().Replace(' ', '-')}.example.com:8006" });

        var status = Get<Dictionary<string, (bool? Online, int? VmCount)>>(w, "_clusterStatus");
        status["Homelab"] = (true, MockVms.Length);
        status["Lab East"] = (true, 4);
        status["DR Site"] = (false, null);
        typeof(MainWindow).GetField("_selectedClusterIdx", F)!.SetValue(w, 0);
        Call(w, "RefreshClusterList");

        var items = Get<ObservableCollection<VmDisplayItem>>(w, "_vmItems");
        items.Clear();
        foreach (var vm in MockVms)
            items.Add(vm);
        if (w.FindName("ClusterTitle") is TextBlock title)
            title.Text = "Homelab";
        Call(w, "OnVmsLoaded", new object?[] { null });
        Pump(600);
    }

    static readonly VmDisplayItem[] MockVms =
    [
        new() { VmId = 101, Name = "win11-dev", Node = "pve1", Pool = "desktops", SnapCount = 3, Status = "running", HasAgent = true, Ips = [("Ethernet", "10.20.30.41"), ("Ethernet 2", "192.168.50.41"), ("Ethernet", "2001:db8:20::41")], OsType = "win11", Notes = "Daily driver" },
        new() { VmId = 102, Name = "fedora-43-ws", Node = "pve1", Pool = "desktops", SnapCount = 1, Status = "running", HasAgent = true, Ips = [("Ethernet", "10.20.30.42")], OsType = "l26", Notes = "", ProxmoxNotes = "## Build workstation\nSee the wiki for the toolchain setup." },
        new() { VmId = 103, Name = "ubuntu-2404-desk", Node = "pve2", Pool = "desktops", SnapCount = 0, Status = "stopped", HasAgent = true, IpNote = "", OsType = "l26", Notes = "" },
        new() { VmId = 110, Name = "kali-lab", Node = "pve2", Pool = "security", SnapCount = 5, Status = "running", HasAgent = false, IpNote = "no agent", OsType = "l26", Notes = "Testing" },
        new() { VmId = 120, Name = "win-server-2025", Node = "pve1", Pool = "servers", SnapCount = 2, Status = "running", HasAgent = true, Ips = [("Ethernet", "10.20.30.60")], OsType = "win11", Notes = "Domain controller" },
        new() { VmId = 121, Name = "debian-13-build", Node = "pve3", Pool = "servers", SnapCount = 0, Status = "stopped", HasAgent = true, IpNote = "", OsType = "l26", Notes = "" },
        new() { VmId = 130, Name = "win10-legacy", Node = "pve3", Pool = "desktops", SnapCount = 1, Status = "stopped", HasAgent = true, IpNote = "", OsType = "win10", Notes = "Keep for old apps" },
        new() { VmId = 140, Name = "arch-sandbox", Node = "pve2", Pool = "", SnapCount = 4, Status = "running", HasAgent = true, Ips = [("Ethernet", "10.20.30.75")], OsType = "l26", Notes = "", ProxmoxNotes = "Reset weekly from the base snapshot" },
    ];

    // Design prototypes: loose XAML files (no code-behind) bound to ProposalData
    static void CaptureProposals(Window w, string dir, string outDir)
    {
        foreach (var file in Directory.GetFiles(dir, "*.xaml").OrderBy(f => f))
        {
            var name = Path.GetFileNameWithoutExtension(file);
            // A prototype drawn with the app's Theme* brushes is captured once per theme, and
            // with its appearance flyout open (if it has one) in every theme and every accent
            if (File.ReadAllText(file).Contains("DynamicResource Theme"))
            {
                var flyout = File.ReadAllText(file).Contains("ShowAppearance");
                foreach (var theme in Themes.All.Keys)
                {
                    ApplyAppearance(theme, "Orange");
                    CaptureProposal(w, file, Path.Combine(outDir, $"proposal-{name}-{Slug(theme)}.png"), false);
                    if (flyout)
                        CaptureProposal(w, file, Path.Combine(outDir, $"proposal-{name}-appearance-{Slug(theme)}.png"), true);
                }
                if (flyout)
                    foreach (var accent in Themes.Accents.Keys)
                    {
                        ApplyAppearance("Catppuccin Mocha", accent);
                        CaptureProposal(w, file, Path.Combine(outDir, $"proposal-{name}-accent-{Slug(accent)}.png"), true);
                    }
                ApplyAppearance("Catppuccin Mocha", "Orange");
            }
            else
                CaptureProposal(w, file, Path.Combine(outDir, $"proposal-{name}.png"), false);
        }
    }

    static void ApplyAppearance(string theme, string accent)
    {
        ThemeManager.Apply(theme, accent);
        ProposalData.Accent = accent;
    }

    static void CaptureProposal(Window w, string file, string path, bool showAppearance)
    {
        using var stream = File.OpenRead(file);
        var element = (FrameworkElement)XamlReader.Load(stream);
        element.DataContext = new ProposalData { ShowAppearance = showAppearance };
        w.SizeToContent = SizeToContent.WidthAndHeight;
        w.Content = element;
        Pump(900);
        Capture(w, path);
        Log($"proposal {Path.GetFileName(path)} captured");
    }

    static string Slug(string s) => s.ToLowerInvariant().Replace(' ', '-');

    static void Capture(Window w, string path)
    {
        // The window's own background is not part of its content, so paint it underneath
        var root = (FrameworkElement)w.Content;
        var rect = new Rect(0, 0, root.ActualWidth, root.ActualHeight);
        var visual = new DrawingVisual();
        using (var dc = visual.RenderOpen())
        {
            dc.DrawRectangle(w.Background, null, rect);
            // Pin the brush to the layout box: effects such as drop shadows widen the visual's
            // bounds, and a stretched brush would shift and shrink everything to fit them
            dc.DrawRectangle(new VisualBrush(root)
            {
                Stretch = Stretch.None,
                ViewboxUnits = BrushMappingMode.Absolute,
                Viewbox = rect,
                ViewportUnits = BrushMappingMode.Absolute,
                Viewport = rect,
            }, null, rect);
        }
        var rtb = new RenderTargetBitmap((int)rect.Width, (int)rect.Height, 96, 96, PixelFormats.Pbgra32);
        rtb.Render(visual);
        var enc = new PngBitmapEncoder();
        enc.Frames.Add(BitmapFrame.Create(rtb));
        using var f = File.Create(path);
        enc.Save(f);
        Console.WriteLine($"wrote {path}");
    }

    static void Pump(int ms)
    {
        var frame = new DispatcherFrame();
        var timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(ms) };
        timer.Tick += (_, _) => { timer.Stop(); frame.Continue = false; };
        timer.Start();
        Dispatcher.PushFrame(frame);
    }
}

public class PCluster
{
    public string Name { get; init; } = "";
    public int? Count { get; init; }
    public bool Online { get; init; }
    public bool Selected { get; init; }
    public string CountText => Count?.ToString() ?? "offline";
}

public class PVm
{
    public int Id { get; init; }
    public string Name { get; init; } = "";
    public bool Windows { get; init; }
    public string OsBadge => Windows ? "WIN" : "LNX";
    public string OsLabel { get; init; } = "";
    public string Node { get; init; } = "";
    public string Pool { get; init; } = "";
    public string Ip { get; init; } = "";
    public int Snaps { get; init; }
    public bool Running { get; init; }
    public string Notes { get; init; } = "";
    public bool Selected { get; init; }
    public bool HasNotes => Notes.Length > 0;
    public bool HasPool => Pool.Length > 0;
    public string Status => Running ? "Running" : "Stopped";
    public string StatusShort => Running ? "RUN" : "OFF";
    public string IpOrDash => Ip.Length > 0 ? Ip : "—";
    public string SnapsText => Snaps == 1 ? "1 snapshot" : $"{Snaps} snapshots";
}

public class PGroup
{
    public string Node { get; init; } = "";
    public List<PVm> Vms { get; init; } = [];
    public string Summary => $"{Vms.Count(v => v.Running)}/{Vms.Count} running";
}

public class PTheme
{
    public string Name { get; init; } = "";
    public Brush Crust { get; init; } = Brushes.Black;
    public Brush Base { get; init; } = Brushes.Black;
    public Brush Surface { get; init; } = Brushes.Black;
    public Brush Text { get; init; } = Brushes.White;
    public Brush Accent { get; init; } = Brushes.Orange;
    public bool Selected { get; init; }
}

public class PAccent
{
    public string Name { get; init; } = "";
    public Brush Brush { get; init; } = Brushes.Orange;
    public bool Selected { get; init; }
}

// Mock data for the prototypes: the same VMs as the real-window shot
public class ProposalData
{
    public List<PCluster> Clusters { get; } =
    [
        new() { Name = "Homelab", Count = 8, Online = true, Selected = true },
        new() { Name = "Lab East", Count = 4, Online = true },
        new() { Name = "DR Site", Count = null, Online = false },
    ];

    public List<PVm> Vms { get; } =
    [
        new() { Id = 101, Name = "win11-dev", Windows = true, OsLabel = "Windows 11", Node = "pve1", Pool = "desktops", Ip = "10.20.30.41", Snaps = 3, Running = true, Notes = "Daily driver", Selected = true },
        new() { Id = 102, Name = "fedora-43-ws", OsLabel = "Linux", Node = "pve1", Pool = "desktops", Ip = "10.20.30.42", Snaps = 1, Running = true },
        new() { Id = 120, Name = "win-server-2025", Windows = true, OsLabel = "Windows Server", Node = "pve1", Pool = "servers", Ip = "10.20.30.60", Snaps = 2, Running = true, Notes = "Domain controller" },
        new() { Id = 103, Name = "ubuntu-2404-desk", OsLabel = "Linux", Node = "pve2", Pool = "desktops", Snaps = 0, Running = false },
        new() { Id = 110, Name = "kali-lab", OsLabel = "Linux", Node = "pve2", Pool = "security", Ip = "no agent", Snaps = 5, Running = true, Notes = "Testing" },
        new() { Id = 140, Name = "arch-sandbox", OsLabel = "Linux", Node = "pve2", Pool = "", Ip = "10.20.30.75", Snaps = 4, Running = true },
        new() { Id = 121, Name = "debian-13-build", OsLabel = "Linux", Node = "pve3", Pool = "servers", Snaps = 0, Running = false },
        new() { Id = 130, Name = "win10-legacy", Windows = true, OsLabel = "Windows 10", Node = "pve3", Pool = "desktops", Snaps = 1, Running = false, Notes = "Keep for old apps" },
    ];

    public List<PGroup> Groups => Vms.GroupBy(v => v.Node).Select(g => new PGroup { Node = g.Key, Vms = g.ToList() }).ToList();
    public int RunningCount => Vms.Count(v => v.Running);
    public int StoppedCount => Vms.Count(v => !v.Running);
    public int TotalCount => Vms.Count;
    public PVm SelectedVm => Vms.First(v => v.Selected);

    // Appearance flyout
    public bool ShowAppearance { get; init; }
    public static string Accent { get; set; } = "Orange";
    public string AccentName => Accent == "Orange" ? "Orange (default)" : Accent;

    public List<PTheme> ThemeChoices => Themes.All.Values.Select(t => new PTheme
    {
        Name = t.Name,
        Crust = new SolidColorBrush(t.Crust),
        Base = new SolidColorBrush(t.Base),
        Surface = new SolidColorBrush(t.Surface1),
        Text = new SolidColorBrush(t.Subtext0),
        Accent = new SolidColorBrush(Themes.AccentColor(t, Accent)),
        Selected = t.Name == ThemeManager.Current.Name,
    }).ToList();

    public List<PAccent> AccentChoices => Themes.Accents.Keys.Select(a => new PAccent
    {
        Name = a,
        Brush = new SolidColorBrush(Themes.AccentColor(ThemeManager.Current, a)),
        Selected = a == Accent,
    }).ToList();
}

