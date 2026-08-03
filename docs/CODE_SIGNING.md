# Code Signing for AirNode

Code signing helps AirNode pass Windows SmartScreen when distributed
commercially. This guide covers obtaining a certificate and signing both
the executable and the installer.

## Why sign?

- Unsigned downloads trigger "Windows protected your PC" SmartScreen blocks.
- Signing builds trust: "Publisher: verified" instead of "Unknown publisher".
- Signatures must match the file hash — tampered copies fail validation.

## Option A: EV Code Signing Certificate (recommended for commercial)

1. Purchase an EV code signing cert from a CA (DigiCert, Sectigo, GlobalSign).
2. The CA issues a hardware USB token (or cloud signing via Azure Trusted Signing).
3. Install the certificate on your build machine or use the vendor's cloud signing API.
4. Configure `signtool` (from the Windows SDK):

```powershell
signtool sign /f .\airnode-cert.pfx /p "your-pfx-password" `
  /t http://timestamp.digicert.com /fd sha256 `
  .\dist\AirNode-1.0.0\AirNode.exe
```

### Automating in build.py

Make signing conditional on a `AIRNODE_SIGN_CERT` environment variable so
the CI/CD pipeline can sign while local builds stay unsigned:

```python
# In build.py, after the exe is produced:
sign_cert = os.environ.get("AIRNODE_SIGN_CERT", "")
if sign_cert:
    subprocess.run([
        "signtool", "sign",
        "/f", sign_cert,
        "/p", os.environ.get("AIRNODE_SIGN_PASSWORD", ""),
        "/t", "http://timestamp.digicert.com",
        "/fd", "sha256",
        str(versioned_exe),
    ], check=True)
```

## Option B: Azure Trusted Signing (cloud, no USB token)

1. Create an Azure account and resource group.
2. Enable Trusted Signing (preview) and request a certificate.
3. Install the trusted-signing-client tools:

```powershell
Install-Module -Name TrustedSigning -Scope CurrentUser -Force
Import-Module TrustedSigning

# Sign the exe
Sign-AirNode -Endpoint "https://eus.codesigning.azure.net" `
  -AccountName "YourAccount" -CertificateProfile "YourProfile" `
  -FilePath ".\dist\AirNode.exe"
```

4. In GitHub Actions, use the `azure/trusted-signing-action`:

```yaml
- uses: azure/trusted-signing-action@v0
  with:
    endpoint: https://eus.codesigning.azure.net
    trusted-signing-account-name: YourAccount
    certificate-profile-name: YourProfile
    files-folder: dist
    files-folder-filter: "*.exe"
```

## Signing the Inno Setup installer

The installer must be signed too — users see the signed Setup.exe in their
browser before they ever install:

```powershell
signtool sign /f .\airnode-cert.pfx /p "your-pfx-password" `
  /t http://timestamp.digicert.com /fd sha256 `
  .\dist\AirNode-Setup-1.0.0.exe
```

In `installer.iss` you can add a `SignTool` directive so Inno Setup signs
automatically during `ISCC`:

```ini
[Setup]
SignTool=signtool /f "C:\certs\airnode-cert.pfx" /p "password" /t http://timestamp.digicert.com /fd sha256 $f
```

## Verifying a signature

```powershell
# Show the signer info
Get-AuthenticodeSignature .\dist\AirNode.exe

# Require trust chain validation
signtool verify /pa /v .\dist\AirNode.exe
```

## SmartScreen trust ramp-up

Even with a signed exe, SmartScreen may show a warning for new publishers
until enough users run the app. This is normal — it fades as downloads
grow. An EV certificate gets instant reputation; a standard OV cert needs
a short ramp-up period.