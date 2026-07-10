using System.Security.Cryptography;
using System.Text;

namespace ProxmoxSpiceManager.Services;

public static class DpapiService
{
    public static string Encrypt(string plaintext)
    {
        var data = Encoding.UTF8.GetBytes(plaintext);
        var encrypted = ProtectedData.Protect(data, null, DataProtectionScope.CurrentUser);
        return Convert.ToBase64String(encrypted);
    }

    public static string? Decrypt(string base64Ciphertext)
    {
        try
        {
            var data = Convert.FromBase64String(base64Ciphertext);
            var decrypted = ProtectedData.Unprotect(data, null, DataProtectionScope.CurrentUser);
            return Encoding.UTF8.GetString(decrypted);
        }
        catch
        {
            return null;
        }
    }
}
