# tpl-arbitro

Árbitro de execução: roda um script Python num ambiente limpo e emite um **veredito selado** que qualquer pessoa pode conferir depois.

Feito para um problema concreto: quando vários modelos de linguagem dizem "executei e passou", ninguém consegue saber se foi verdade. O árbitro troca a afirmação por evidência.

## O que ele garante (em código)

1. **Recusa arquivo corrompido** — detecta sinais de código colado no Google Docs (`from future import`, `def init(self`, `if name == "main"`), registra BOM e CRLF.
2. **Identidade por hash** — SHA-256 dos bytes exatos; compara com o hash informado.
3. **Autor ≠ executor** — quem escreveu o código nunca gera `VERIFICADO` sozinho.
4. **Execução isolada** — diretório novo e vazio, `python -I`, ambiente mínimo, timeout; guarda stdout, stderr e código de saída reais.
5. **Só quatro estados** — `VERIFICADO`, `DIVERGENTE`, `NAO EXECUTADO`, `MENCIONADO`. Sem booleanos.
6. **Nunca sobrescreve** um veredito existente; cada veredito tem selo SHA-256.

## Uso

```bash
python3 -I tpl_arbitro.py autoteste

python3 -I tpl_arbitro.py arbitrar script.py --autor ModeloA --executor ModeloB \
    --esperar-exit 0 --esperar "OK" --hash-informado <sha256> --timeout 300

python3 -I tpl_arbitro.py conferir VEREDITO_script.txt
```

Só biblioteca padrão. O autoteste (12 testes) roda no GitHub Actions a cada envio.

## Limite

O árbitro registra quem o usuário **diz** que é autor e executor; não prova identidade. A execução cruzada entre modelos continua necessária — o GitHub Actions serve como um executor independente.

---
Parte do ecossistema [TPL](https://github.com/Eduardo77117711/-tpl-).

Criado por Carlos Eduardo Acevedo Rodrigues. Copyright 2026.
Licenciado sob a [GNU AGPL-3.0](LICENSE): livre para usar, estudar, modificar e redistribuir. Toda versão derivada, inclusive a oferecida como serviço pela internet, continua livre sob a mesma licença e deve manter esta atribuição e o arquivo [NOTICE](NOTICE).
