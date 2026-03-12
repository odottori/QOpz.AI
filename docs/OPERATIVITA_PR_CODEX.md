# Operatività PR con Codex (workflow pratico)

## TL;DR
**No:** non devi premere tu il pulsante **"Create PR"** nella UI di Codex.

In questo progetto il flusso è:
1. Codex implementa le modifiche.
2. Codex esegue test/check.
3. Codex fa `git commit` sul branch corrente.
4. Codex registra la PR via tool `make_pr` (titolo + body).

## Quando serve azione umana
L'azione manuale può servire solo in casi infrastrutturali, per esempio:
- il repository locale non ha remote/upstream configurato;
- policy di piattaforma richiede una revisione/manual gate esterno;
- credenziali/token non presenti nell'ambiente runtime.

In questi casi Codex lo segnala esplicitamente nei check (es. stato repo sync / push readiness).

## Regola operativa consigliata
- Tu dai priorità/requisiti.
- Codex esegue patch + commit + registrazione PR.
- Tu valuti risultato e feedback tecnico/prodotto.


## Se hai già creato/mergeato manualmente in un'altra chat
Non hai fatto "casini": in molti contesti è una pratica normale.

La differenza è solo di **modalità operativa**:
- in alcuni flussi l'agente prepara patch e l'umano crea/mergea;
- in questo flusso, quando possibile, Codex fa commit + registrazione PR in autonomia.

Quindi il comportamento passato non è sbagliato: è solo un workflow diverso.
