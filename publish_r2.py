"""
Publica o .exe e o instalador no espelho Cloudflare R2 -- canal alternativo
de auto-update, usado quando o GitHub está bloqueado/inacessível na rede
(foi o caso do PC do estúdio). Sobe pro MESMO bucket "app-releases" que o
PlayTranscription já usa (ver ../PlayTranscription/scripts/publish-cloudflare.mjs),
só que no prefixo "autotrigger" -- bucket com acesso público já habilitado
(pub-8060....r2.dev), então não precisa reconfigurar nada no painel.

O endpoint abaixo é a API S3 (autenticada, só usada aqui pra fazer upload).
A URL que o app CONSULTA em runtime é outra, pública, sem autenticação
(CLOUDFLARE_UPDATE_URL em version.py) -- só ela fica gravada no .exe.

Credenciais só por variável de ambiente (NUNCA hardcoded aqui):
  R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY

Uso (depois de build.bat ter gerado dist\\AutoTriggerV10.exe):
    set R2_ACCESS_KEY_ID=...
    set R2_SECRET_ACCESS_KEY=...
    python publish_r2.py

Requer boto3 (só ferramenta de build -- não vai para o .exe empacotado,
não precisa estar em requirements.txt): pip install boto3
"""
import json
import os
import sys

try:
    import boto3
except ImportError:
    print("Falta o boto3 (só para publicar): pip install boto3")
    sys.exit(1)

from version import __version__, GITHUB_ASSET_NAME

R2_ENDPOINT = "https://3ba41e8e3fe261af1fe20455343c36d1.r2.cloudflarestorage.com"
R2_BUCKET = "app-releases"
R2_PREFIX = "autotrigger"
R2_PUBLIC_BASE = f"https://pub-8060abbe70084968817647c74ce4ffbc.r2.dev/{R2_PREFIX}"

_HERE = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(_HERE, "dist")

_CONTENT_TYPES = {".exe": "application/octet-stream", ".json": "application/json"}


def _upload(s3, local_path: str, key: str, content_type: str | None = None, data: bytes | None = None):
    if content_type is None:
        content_type = _CONTENT_TYPES.get(os.path.splitext(local_path)[1].lower(), "application/octet-stream")
    if data is None:
        size = os.path.getsize(local_path)
        print(f"Enviando {os.path.basename(local_path)} ({size / 1_000_000:.1f} MB) -> {R2_BUCKET}/{key}")
        with open(local_path, "rb") as f:
            s3.put_object(Bucket=R2_BUCKET, Key=key, Body=f, ContentType=content_type)
        return size
    else:
        print(f"Enviando {key} -> {R2_BUCKET}/{key}")
        s3.put_object(Bucket=R2_BUCKET, Key=key, Body=data, ContentType=content_type)
        return len(data)


def main():
    access_key = os.environ.get("R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not access_key or not secret_key:
        print("Faltam as variáveis de ambiente R2_ACCESS_KEY_ID e/ou R2_SECRET_ACCESS_KEY.")
        sys.exit(1)

    exe_path = os.path.join(DIST_DIR, GITHUB_ASSET_NAME)
    if not os.path.exists(exe_path):
        print(f"Não encontrado: {exe_path}. Rode build.bat antes.")
        sys.exit(1)

    installer_name = f"AutoTriggerV10_Setup_v{__version__}.exe"
    installer_path = os.path.join(DIST_DIR, installer_name)

    notes_path = os.path.join(_HERE, "RELEASE_NOTES.md")
    notes = ""
    if os.path.exists(notes_path):
        with open(notes_path, "r", encoding="utf-8") as f:
            notes = f.read()

    s3 = boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )

    exe_size = _upload(s3, exe_path, f"{R2_PREFIX}/{GITHUB_ASSET_NAME}")

    installer_url = ""
    if os.path.exists(installer_path):
        _upload(s3, installer_path, f"{R2_PREFIX}/{installer_name}")
        installer_url = f"{R2_PUBLIC_BASE}/{installer_name}"
    else:
        print(f"AVISO: instalador não encontrado ({installer_path}) -- publicando só o .exe.")

    manifest = {
        "version": __version__,
        "notes": notes,
        "exe_url": f"{R2_PUBLIC_BASE}/{GITHUB_ASSET_NAME}",
        "installer_url": installer_url,
        "size": exe_size,
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    _upload(s3, "", f"{R2_PREFIX}/latest.json", content_type="application/json", data=manifest_bytes)

    print()
    print(f"Publicado v{__version__} no Cloudflare R2:")
    print(f"  {R2_PUBLIC_BASE}/latest.json")
    print(f"  {manifest['exe_url']}")
    if installer_url:
        print(f"  {installer_url}")


if __name__ == "__main__":
    main()
