using System.Windows;
using ProxmoxSpiceManager.Services;

namespace ProxmoxSpiceManager;

public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        var config = ConfigService.Load();
        ThemeManager.Apply(config.Theme);
    }
}
