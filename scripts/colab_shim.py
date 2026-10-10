"""
Shim de compatibilidade: substitui `google.colab.drive` e
`google.colab.userdata` para os scripts originais (escritos para rodar
como célula do Colab) funcionarem sem alteração de lógica fora dele.

Nos scripts adaptados, a única mudança de import é:
    from google.colab import drive, userdata     # antes
    from colab_shim import drive, userdata       # depois

- drive.mount(...) não faz mais nada (não usamos Google Drive).
- userdata.get(nome) lê a variável de ambiente `nome` (populada pelo
  .env local via config.py, ou por Secrets do GitHub Actions).

BASE_DRIVE, nos scripts adaptados, aponta para uma pasta local do
repositório (dados_raw/) em vez de '/content/drive/MyDrive/...'.
"""
import os

# Carrega o .env local, se existir (não faz nada em CI/produção, onde as
# variáveis já vêm setadas pelo ambiente). override=True: o .env sempre
# vence sobre uma variável de ambiente antiga/residual do shell -- mesma
# lógica de config.py, para os dois nunca divergirem.
try:
    from dotenv import load_dotenv

    if not os.environ.get('IGNORAR_DOTENV'):
        load_dotenv(override=True)
except ImportError:
    pass


class _Drive:
    def mount(self, *args, **kwargs):
        # no-op: não montamos mais o Google Drive
        pass


class _Userdata:
    def get(self, nome):
        return os.environ.get(nome)


drive = _Drive()
userdata = _Userdata()
