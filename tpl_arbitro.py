#!/usr/bin/env python3
"""tpl_arbitro.py — o TPL_PROTOCOLO_UNIFICADO transformado em código.

Versão 1. AUTOR: Claude (Árbitro 2). Pela regra 4 do TPL, esta ferramenta só
vira oficial depois de verificada por outro executor.

Uso:
  python3 -I tpl_arbitro.py arbitrar ARQUIVO.py --autor A --executor E \
      [--esperar-exit 0] [--esperar "texto"]... [--hash-informado SHA] \
      [--timeout 300] [--saida DIR] -- [argumentos do ARQUIVO]
  python3 -I tpl_arbitro.py conferir VEREDITO_x.txt
  python3 -I tpl_arbitro.py autoteste

Regras aplicadas pelo código (numeração do TPL_PROTOCOLO_UNIFICADO):
  2  recusa arquivo com sinais de Google Doc (sublinhados perdidos, linhas
     juntadas, sintaxe quebrada); registra BOM e CRLF.
  3  identidade por sha256 dos bytes exatos; compara com o hash informado.
  4  autor == executor nunca gera VERIFICADO.
  5  execução em diretório novo e vazio, python -I, ambiente mínimo, timeout;
     stdout, stderr e código de saída reais; versões registradas.
  6  só quatro estados: VERIFICADO, DIVERGENTE, NAO EXECUTADO, MENCIONADO.
  7  nunca sobrescreve um veredito existente.

Limite: a ferramenta registra quem o usuário diz que é autor e executor; ela
não consegue provar identidade. A execução cruzada entre modelos continua
necessária.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

VERSAO = "1"
VERIFICADO = "VERIFICADO"
DIVERGENTE = "DIVERGENTE"
NAO_EXECUTADO = "NAO EXECUTADO"
MENCIONADO = "MENCIONADO"
ESTADOS = (VERIFICADO, DIVERGENTE, NAO_EXECUTADO, MENCIONADO)
LIMITE_SAIDA = 20000
PREFIXO_SELO = "SELO: sha256 do corpo (todas as linhas acima desta) = "

SINAIS_DE_DOC = (
    (re.compile(r"^\s*from\s+future\s+import", re.M), "'from future import' (sublinhados de __future__ perdidos)"),
    (re.compile(r"\bdef\s+init\s*\(\s*self"), "'def init(self' (sublinhados de __init__ perdidos)"),
    (re.compile(r"\bif\s+name\s*==\s*['\"]main['\"]"), "'if name == \"main\"' (sublinhados de __name__/__main__ perdidos)"),
)


def sha256_bytes(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def agora_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def mesmo_agente(a: str, b: str) -> bool:
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    return norm(a) == norm(b)


def inspecionar_formato(dados: bytes) -> tuple[list[str], list[str]]:
    """Retorna (bloqueios, avisos) sobre o formato do arquivo."""
    bloqueios: list[str] = []
    avisos: list[str] = []
    if dados.startswith(b"\xef\xbb\xbf"):
        avisos.append("arquivo começa com BOM UTF-8 (típico de exportação de Doc)")
    if b"\r\n" in dados:
        avisos.append("quebras de linha CRLF (típico de exportação de Doc)")
    try:
        texto = dados.decode("utf-8-sig")
    except UnicodeDecodeError:
        return ["arquivo não é UTF-8 válido"], avisos
    for padrao, descricao in SINAIS_DE_DOC:
        if padrao.search(texto):
            bloqueios.append(f"sinal de Google Doc: {descricao}")
    linhas = texto.splitlines()
    if linhas and len(linhas) < 5 and max(len(l) for l in linhas) > 2000:
        bloqueios.append("código em poucas linhas muito longas (linhas juntadas)")
    try:
        compile(texto, "<entrada>", "exec")
    except SyntaxError as exc:
        bloqueios.append(f"sintaxe inválida: {exc.msg} (linha {exc.lineno})")
    return bloqueios, avisos


@dataclass
class Execucao:
    comando: list[str]
    codigo_saida: int | None
    stdout: str
    stderr: str
    timeout: bool = False


def ambiente_minimo(diretorio: str) -> dict[str, str]:
    return {"PATH": os.environ.get("PATH", os.defpath) if os.name == "nt" else "/usr/bin:/bin",
            "HOME": diretorio, "TMPDIR": diretorio, "TEMP": diretorio, "TMP": diretorio}


def executar(arquivo: Path, argumentos: list[str], timeout: int) -> Execucao:
    with tempfile.TemporaryDirectory(prefix="tpl_") as tmp:
        alvo = Path(tmp) / arquivo.name
        shutil.copyfile(arquivo, alvo)
        comando = [sys.executable, "-I", alvo.name, *argumentos]
        try:
            proc = subprocess.run(comando, cwd=tmp, env=ambiente_minimo(tmp),
                                  capture_output=True, timeout=timeout)
            return Execucao(comando, proc.returncode,
                            proc.stdout.decode("utf-8", "replace"),
                            proc.stderr.decode("utf-8", "replace"))
        except subprocess.TimeoutExpired as exc:
            return Execucao(comando, None,
                            (exc.stdout or b"").decode("utf-8", "replace"),
                            (exc.stderr or b"").decode("utf-8", "replace"), timeout=True)


def versoes_ambiente() -> str:
    codigo = ("import sys\nprint('Python', sys.version.split()[0])\n"
              "for m in ('numpy','scipy'):\n"
              "    try:\n        mod=__import__(m); print(m, mod.__version__)\n"
              "    except Exception: print(m, 'ausente')\n")
    with tempfile.TemporaryDirectory(prefix="tpl_v_") as tmp:
        proc = subprocess.run([sys.executable, "-I", "-c", codigo], cwd=tmp,
                              env=ambiente_minimo(tmp), capture_output=True, timeout=60)
    return proc.stdout.decode("utf-8", "replace").strip()


@dataclass
class Decisao:
    estado: str
    motivos: list[str] = field(default_factory=list)
    nota: str = ""


def decidir(bloqueios: list[str], execucao: Execucao | None, autor: str, executor: str,
            esperar_exit: int | None, esperar: list[str],
            hash_arquivo: str, hash_informado: str | None) -> Decisao:
    if hash_informado and hash_informado.lower() != hash_arquivo:
        return Decisao(DIVERGENTE, [f"hash informado {hash_informado} difere do hash dos bytes {hash_arquivo}"])
    if bloqueios:
        return Decisao(NAO_EXECUTADO, bloqueios)
    if execucao is None:
        return Decisao(NAO_EXECUTADO, ["execução não realizada"])
    if esperar_exit is None and not esperar:
        return Decisao(MENCIONADO, ["sem critério COMO_CONFERIR (--esperar-exit/--esperar)"])
    falhas: list[str] = []
    if execucao.timeout:
        falhas.append("tempo limite excedido")
    elif esperar_exit is not None and execucao.codigo_saida != esperar_exit:
        falhas.append(f"código de saída {execucao.codigo_saida}, esperado {esperar_exit}")
    saida_total = execucao.stdout + "\n" + execucao.stderr
    for texto in esperar:
        if texto not in saida_total:
            falhas.append(f"texto esperado ausente: {texto!r}")
    resultado = "bateu com o critério" if not falhas else "não bateu com o critério"
    if mesmo_agente(autor, executor):
        return Decisao(NAO_EXECUTADO,
                       [f"executor ({executor}) é o próprio autor; regra 4 impede VERIFICADO"],
                       nota=f"relato do autor: execução {resultado}" + (f" ({'; '.join(falhas)})" if falhas else ""))
    if falhas:
        return Decisao(DIVERGENTE, falhas)
    return Decisao(VERIFICADO, ["executor independente; saída bateu com o critério"])


def cortar(texto: str) -> str:
    if len(texto) <= LIMITE_SAIDA:
        return texto
    return texto[:LIMITE_SAIDA] + f"\n[... cortado: {len(texto) - LIMITE_SAIDA} caracteres omitidos]"


def montar_corpo(nome_arquivo: str, hash_arquivo: str, tamanho: int, autor: str, executor: str,
                 hash_informado: str | None, avisos: list[str], versoes: str,
                 execucao: Execucao | None, esperar_exit: int | None, esperar: list[str],
                 decisao: Decisao) -> str:
    l: list[str] = []
    l.append(f"VEREDITO_{nome_arquivo}.txt")
    l.append(f"Gerado por tpl_arbitro.py versão {VERSAO}")
    l.append(f"DATA_UTC: {agora_utc()}")
    l.append(f"AUTOR: {autor}")
    l.append(f"EXECUTOR: {executor} (declarado; a ferramenta não prova identidade)")
    l.append("")
    l.append(f"ARQUIVO: {nome_arquivo} ({tamanho} bytes)")
    l.append(f"SHA256: {hash_arquivo}")
    l.append(f"HASH_INFORMADO: {hash_informado or 'não informado'}"
             + ("" if not hash_informado else (" -> IGUAL" if hash_informado.lower() == hash_arquivo else " -> DIFERENTE")))
    for aviso in avisos:
        l.append(f"AVISO_FORMATO: {aviso}")
    l.append("")
    l.append("AMBIENTE:")
    l.append(versoes or "(não obtido)")
    l.append("")
    l.append("COMO_CONFERIR:")
    l.append(f"  código de saída esperado: {esperar_exit if esperar_exit is not None else 'não definido'}")
    for texto in esperar:
        l.append(f"  texto esperado: {texto}")
    l.append("")
    if execucao is not None:
        l.append("COMANDO (em diretório novo e vazio, ambiente mínimo):")
        l.append("  " + " ".join(execucao.comando))
        l.append(f"CODIGO_DE_SAIDA: {'TIMEOUT' if execucao.timeout else execucao.codigo_saida}")
        l.append("STDOUT (integral):")
        l.append(cortar(execucao.stdout).rstrip("\n"))
        l.append("STDERR (integral):")
        l.append(cortar(execucao.stderr).rstrip("\n"))
    else:
        l.append("COMANDO: nenhum (não executado)")
    l.append("")
    l.append(f"ESTADO: {decisao.estado}")
    for motivo in decisao.motivos:
        l.append(f"MOTIVO: {motivo}")
    if decisao.nota:
        l.append(f"NOTA: {decisao.nota}")
    return "\n".join(l) + "\n"


def selar(corpo: str) -> str:
    return corpo + PREFIXO_SELO + sha256_bytes(corpo.encode("utf-8")) + "\n"


def conferir_selo(texto: str) -> tuple[bool, str]:
    if not texto.endswith("\n"):
        return False, "arquivo não termina em quebra de linha"
    linhas = texto[:-1].split("\n")
    ultima = linhas[-1]
    if not ultima.startswith(PREFIXO_SELO):
        return False, "última linha não é um SELO"
    informado = ultima[len(PREFIXO_SELO):].strip()
    corpo = "\n".join(linhas[:-1]) + "\n"
    calculado = sha256_bytes(corpo.encode("utf-8"))
    if informado == calculado:
        return True, f"SELO confere ({calculado})"
    return False, f"SELO NAO confere: informado {informado}, calculado {calculado}"


def arbitrar(arquivo: Path, autor: str, executor: str, argumentos: list[str],
             esperar_exit: int | None, esperar: list[str], hash_informado: str | None,
             timeout: int, saida: Path) -> tuple[Path, Decisao]:
    dados = arquivo.read_bytes()
    hash_arquivo = sha256_bytes(dados)
    destino = saida / f"VEREDITO_{arquivo.name}.txt"
    if destino.exists():
        raise FileExistsError(f"{destino} já existe; o TPL não sobrescreve vereditos (use um ADENDO)")
    bloqueios, avisos = inspecionar_formato(dados)
    hash_ok = not hash_informado or hash_informado.lower() == hash_arquivo
    execucao = executar(arquivo, argumentos, timeout) if (not bloqueios and hash_ok) else None
    versoes = versoes_ambiente()
    decisao = decidir(bloqueios, execucao, autor, executor, esperar_exit, esperar,
                      hash_arquivo, hash_informado)
    corpo = montar_corpo(arquivo.name, hash_arquivo, len(dados), autor, executor, hash_informado,
                         avisos, versoes, execucao, esperar_exit, esperar, decisao)
    saida.mkdir(parents=True, exist_ok=True)
    with destino.open("x", encoding="utf-8", newline="\n") as f:
        f.write(selar(corpo))
    return destino, decisao


# ----------------------------------------------------------------- autotestes
class TplArbitroTests(unittest.TestCase):
    def _arbitrar(self, codigo: str, autor="ChatGPT", executor="Claude", args=(),
                  esperar_exit=0, esperar=("OK-FIM",), hash_informado=None, timeout=60):
        with tempfile.TemporaryDirectory() as tmp:
            alvo = Path(tmp) / "alvo.py"
            alvo.write_bytes(codigo.encode("utf-8"))
            destino, decisao = arbitrar(alvo, autor, executor, list(args), esperar_exit,
                                        list(esperar), hash_informado, timeout, Path(tmp) / "out")
            texto = destino.read_text(encoding="utf-8")
            return decisao, texto

    def test_verificado_com_executor_independente(self):
        d, t = self._arbitrar("print('OK-FIM')\n")
        self.assertEqual(d.estado, VERIFICADO)
        self.assertTrue(conferir_selo(t)[0])
        self.assertIn("CODIGO_DE_SAIDA: 0", t)

    def test_autor_igual_executor_nunca_verifica(self):
        d, _ = self._arbitrar("print('OK-FIM')\n", autor="Claude", executor="claude ")
        self.assertEqual(d.estado, NAO_EXECUTADO)
        self.assertIn("regra 4", d.motivos[0])

    def test_codigo_de_saida_diferente_diverge(self):
        d, _ = self._arbitrar("import sys\nprint('OK-FIM')\nsys.exit(3)\n")
        self.assertEqual(d.estado, DIVERGENTE)
        self.assertIn("código de saída 3", d.motivos[0])

    def test_texto_ausente_diverge(self):
        d, _ = self._arbitrar("print('outra coisa')\n")
        self.assertEqual(d.estado, DIVERGENTE)

    def test_sem_criterio_e_mencionado(self):
        d, _ = self._arbitrar("print('x')\n", esperar_exit=None, esperar=())
        self.assertEqual(d.estado, MENCIONADO)

    def test_formato_de_doc_bloqueia(self):
        quebrado = 'from future import annotations\nclass A:\n    def init(self): pass\nif name == "main": pass\n'
        d, t = self._arbitrar(quebrado)
        self.assertEqual(d.estado, NAO_EXECUTADO)
        self.assertIn("COMANDO: nenhum", t)
        self.assertTrue(any("__init__" in m for m in d.motivos))

    def test_sintaxe_quebrada_bloqueia(self):
        d, _ = self._arbitrar("def f(:\n")
        self.assertEqual(d.estado, NAO_EXECUTADO)

    def test_hash_informado_diferente_diverge_sem_executar(self):
        d, t = self._arbitrar("print('OK-FIM')\n", hash_informado="0" * 64)
        self.assertEqual(d.estado, DIVERGENTE)
        self.assertIn("COMANDO: nenhum", t)

    def test_timeout_diverge(self):
        d, t = self._arbitrar("import time\ntime.sleep(10)\n", timeout=1)
        self.assertEqual(d.estado, DIVERGENTE)
        self.assertIn("CODIGO_DE_SAIDA: TIMEOUT", t)

    def test_ambiente_minimo_sem_variaveis_herdadas(self):
        os.environ["TPL_SEGREDO_TESTE"] = "vazou"
        try:
            d, t = self._arbitrar("import os\nprint('OK-FIM', os.environ.get('TPL_SEGREDO_TESTE'))\n",
                                  esperar=("OK-FIM None",))
        finally:
            del os.environ["TPL_SEGREDO_TESTE"]
        self.assertEqual(d.estado, VERIFICADO)

    def test_selo_detecta_alteracao(self):
        texto = selar("linha 1\nESTADO: DIVERGENTE\n")
        self.assertTrue(conferir_selo(texto)[0])
        self.assertFalse(conferir_selo(texto.replace("DIVERGENTE", "VERIFICADO"))[0])

    def test_nao_sobrescreve_veredito(self):
        with tempfile.TemporaryDirectory() as tmp:
            alvo = Path(tmp) / "alvo.py"
            alvo.write_text("print('OK-FIM')\n", encoding="utf-8")
            arbitrar(alvo, "A", "B", [], 0, ["OK-FIM"], None, 60, Path(tmp))
            with self.assertRaises(FileExistsError):
                arbitrar(alvo, "A", "B", [], 0, ["OK-FIM"], None, 60, Path(tmp))


# ----------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    extras: list[str] = []
    if "--" in argv:
        i = argv.index("--")
        argv, extras = argv[:i], argv[i + 1:]
    p = argparse.ArgumentParser(prog="tpl_arbitro.py", description="Árbitro do TPL")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("arbitrar")
    a.add_argument("arquivo", type=Path)
    a.add_argument("--autor", required=True)
    a.add_argument("--executor", required=True)
    a.add_argument("--esperar-exit", type=int, default=None)
    a.add_argument("--esperar", action="append", default=[])
    a.add_argument("--hash-informado", default=None)
    a.add_argument("--timeout", type=int, default=300)
    a.add_argument("--saida", type=Path, default=Path("."))
    c = sub.add_parser("conferir")
    c.add_argument("veredito", type=Path)
    sub.add_parser("autoteste")
    args = p.parse_args(argv)

    if args.cmd == "autoteste":
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(TplArbitroTests)
        ok = unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
        print(f"AUTOTESTE_TPL_ARBITRO: {'PASSOU' if ok else 'FALHOU'}")
        return 0 if ok else 1
    if args.cmd == "conferir":
        ok, msg = conferir_selo(args.veredito.read_text(encoding="utf-8"))
        print(msg)
        return 0 if ok else 1
    destino, decisao = arbitrar(args.arquivo, args.autor, args.executor, extras,
                                args.esperar_exit, args.esperar, args.hash_informado,
                                args.timeout, args.saida)
    print(f"ESTADO: {decisao.estado}")
    for m in decisao.motivos:
        print(f"MOTIVO: {m}")
    if decisao.nota:
        print(f"NOTA: {decisao.nota}")
    print(f"VEREDITO gravado em: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
