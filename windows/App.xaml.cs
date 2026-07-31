using System.Threading;
using System.Windows;
using ProxmoxSpiceManager.Services;

namespace ProxmoxSpiceManager;

public partial class App : Application
{
    private static Mutex? _mutex;

    protected override void OnStartup(StartupEventArgs e)
    {
        _mutex = new Mutex(true, "ProxmoxSpiceManager_SingleInstance", out bool isNew);
        if (!isNew)
        {
            MessageBox.Show("Proxmox SPICE Manager is already running.",
                "Already Running", MessageBoxButton.OK, MessageBoxImage.Information);
            Shutdown();
            return;
        }

        base.OnStartup(e);
        var config = ConfigService.Load();
        ThemeManager.Apply(config.Theme);
        DebugLogger.SetEnabled(config.DebugLogging);
    }
}
