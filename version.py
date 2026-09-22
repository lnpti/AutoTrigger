"""
Versao do AutoTrigger V10.
Este arquivo e a unica fonte da versao -- nao editar manualmente.
O build.bat e o sistema de auto-update usam este valor.
"""

__version__ = "2.3.20"

# Repositório GitHub usado pelo auto-updater
GITHUB_REPO = "lnpti/AutoTrigger"

# Nome do asset no GitHub Release que contém o executável compilado
GITHUB_ASSET_NAME = "AutoTriggerV10.exe"

# Espelho de atualização no Cloudflare R2 (reserva quando o GitHub está
# bloqueado/inacessível na rede -- foi o caso do PC do estúdio). URL pública
# (bucket com acesso público habilitado), sem autenticação -- não é segredo.
# Publicado por publish_r2.py a cada release, junto do GitHub.
CLOUDFLARE_UPDATE_URL = "https://pub-8060abbe70084968817647c74ce4ffbc.r2.dev/autotrigger/latest.json"
