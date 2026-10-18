"""
Correção das quedas nativas "Windows fatal exception: access violation" vistas no
crash.log do estúdio, sempre com esta pilha:

    Garbage-collecting
      comtypes\\_post_coinit\\unknwn.py  in Release
      comtypes\\_post_coinit\\unknwn.py  in __del__

O comtypes chama Release() de dentro do __del__ de cada ponteiro COM. Quando o
coletor de lixo do Python libera um desses ponteiros numa thread DIFERENTE da que o
criou (ou depois que a thread criadora terminou, desfazendo o apartamento COM),
o Release() acessa memória inválida e derruba o processo inteiro -- sem exceção
Python, sem aviso. Reproduzido em teste (ponteiros criados em threads que acabam e
liberados pelo GC de outra).

O app cria poucos objetos COM e pequenos (mute, lista de dispositivos, medidor de
áudio), então a solução é NÃO liberar automaticamente: o `__del__` dos ponteiros
vira no-op e o Windows recolhe tudo quando o processo termina. Importar este módulo
ANTES de qualquer uso do pycaw/comtypes.
"""
from ctypes import POINTER

import comtypes


def _patch() -> bool:
    # O __del__ fica na classe base dos PONTEIROS (_compointer_base), não em IUnknown.
    for cls in POINTER(comtypes.IUnknown).__mro__:
        if "__del__" in vars(cls) and cls.__name__ == "_compointer_base":
            cls.__del__ = lambda self: None
            return True
    return False


PATCHED = _patch()
