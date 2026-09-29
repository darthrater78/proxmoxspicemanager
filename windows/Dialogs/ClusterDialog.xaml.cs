using System.Windows;
using ProxmoxSpiceManager.Models;
using ProxmoxSpiceManager.Services;

namespace ProxmoxSpiceManager.Dialogs;

public partial class ClusterDialog : Window
{
    private readonly AppConfig _config;
    private readonly ClusterConfig? _existing;
    private string? _pin;

    public ClusterConfig? Result { get; private set; }
    public string? PendingSecret { get; private set; }

    public ClusterDialog(AppConfig config, ClusterConfig? existing = null)
    {
        InitializeComponent();
        _config = config;
        _existing = existing;

        if (existing != null)
        {
            Title = "Edit Cluster";
            NameBox.Text = existing.Name;
            HostBox.Text = existing.Host;
            _pin = existing.TlsFingerprint;

            if (existing.AuthMethod == "password")
            {
                PasswordRadio.IsChecked = true;
                UsernameBox.Text = existing.Username;
            }
            else
            {
                TokenRadio.IsChecked = true;
                TokenIdBox.Text = existing.TokenId;
                var secret = ConfigService.GetSecret(existing);
                if (secret != null)
                    TokenSecretBox.Password = secret;
            }
        }

        ShowPin();
        NameBox.Focus();
    }

    private void ShowPin()
    {
        CertText.Text = _pin != null
            ? $"Certificate pinned: {_pin[..Math.Min(23, _pin.Length)]}…"
            : "Certificate: checked by this system. A self-signed one is shown for you to confirm on first connect.";
        ForgetPinBtn.Visibility = _pin != null ? Visibility.Visible : Visibility.Collapsed;
    }

    private void OnForgetPin(object sender, RoutedEventArgs e)
    {
        _pin = null;
        ShowPin();
    }

    private void OnAuthChanged(object sender, RoutedEventArgs e)
    {
        if (TokenPanel == null) return;
        TokenPanel.Visibility = TokenRadio.IsChecked == true ? Visibility.Visible : Visibility.Collapsed;
        PasswordPanel.Visibility = PasswordRadio.IsChecked == true ? Visibility.Visible : Visibility.Collapsed;
    }

    private void OnSave(object sender, RoutedEventArgs e)
    {
        var name = NameBox.Text.Trim();
        var host = HostBox.Text.Trim().TrimEnd('/');

        if (string.IsNullOrEmpty(name) || string.IsNullOrEmpty(host))
        {
            MessageBox.Show("Name and Host URL are required.", "Missing Fields",
                MessageBoxButton.OK, MessageBoxImage.Warning);
            return;
        }

        if (!Uri.TryCreate(host, UriKind.Absolute, out var uri) ||
            uri.Scheme != Uri.UriSchemeHttps || string.IsNullOrEmpty(uri.Host))
        {
            MessageBox.Show("The host URL must start with https://, for example\nhttps://pve.example.com:8006",
                "Invalid Host URL", MessageBoxButton.OK, MessageBoxImage.Warning);
            return;
        }

        var authMethod = TokenRadio.IsChecked == true ? "token" : "password";
        var secret = TokenSecretBox.Password;

        PendingSecret = authMethod == "token" && !string.IsNullOrEmpty(secret) ? secret : null;

        Result = new ClusterConfig
        {
            Name = name,
            Host = host,
            AuthMethod = authMethod,
            TokenId = TokenIdBox.Text.Trim(),
            Username = UsernameBox.Text.Trim(),
            // A pin belongs to the host it was confirmed for
            TlsFingerprint = _existing != null && host == _existing.Host ? _pin : null,
            TokenSecretEnc = _existing?.TokenSecretEnc,
        };

        DialogResult = true;
    }

    private void OnCancel(object sender, RoutedEventArgs e)
    {
        DialogResult = false;
    }
}
