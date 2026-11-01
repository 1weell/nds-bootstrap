# Caminho até a build funcional — 01-11-2026

## Resultado físico

Baseline v7.3: usuário confirmou Kirby identificado corretamente no startup,
três achievements reais com nomes completos e scroll horizontal, estabilidade
visual e identificação correta de Advance Wars. Não há confirmação registrada
pelo servidor dos três awards nem testes completos em todos os jogos/modos.

## Evolução, falhas e decisões

1. Tentativas anteriores com BG/OAM/VRAM DS conflitavam com recursos dos jogos.
   A janela ARM11/TwlBg preservou independência dos gráficos DS.
2. Antigravity v6 demonstrou popup no console via OCR. Porém, dois pixels brancos
   podiam trocar classificação de unlock por startup; Spark/Fire próximos
   perdiam o segundo evento; banner persistente podia repetir notificação.
3. OCR não recuperava nome canônico ausente nem texto já cortado no parser.
   Decisão: eventos tipados do runtime RA, OCR somente experimental.
4. Parser passou a distinguir PatchData.Title de Title de achievement, decodificar
   Unicode/surrogate pairs e preservar 95 bytes UTF-8 sem cortar codepoints.
   Cache .meta associa hash/GameID/revisão/nome, CRC e geração anterior recuperável.
5. Sessão mantém offsets antigos e reserva de 256 bytes. Nome visual separado do
   header de ROM de 12 bytes usado pela fila persistente.
6. Bridge: BEGIN/READY/UNLOCK/PREVIEW/END, sessão, sequência, IDs e CRC. ARM9 copia
   cada trigger; ARM7 usa slot 12 e RTC 112/113; ARM11 mantém FIFO/deduplicação.
   Backpressure/timeout limitados preservam avaliação e fila de awards.
7. Política overlay off/lista/todos separada de renderer arm11/legacy. Sem peer
   não reativa automaticamente empréstimo de recursos gráficos DS.
8. Footprint: variantes ARM7 TWLSDK usam Os em serviço/clock/menu, com guard de
   stack. Remoção de asserts de debug em dois módulos rcheevos evitou dependência
   grande de stderr/heap. Guard real de margem >8192 bytes permaneceu.
9. v7 passou em modelo, mas não mostrou popup. Teste serial repetia suposição
   errada de libnds: parâmetros normais RTC LSB-first, extensão RTCom MSB-first.
   Fixture independente revelou 01 virando 80 e HELLO 50 virando 0A. Corrigido na
   v7.1; hardware confirmou startup/preview, ainda com flicker.
10. v7.2 tentou três saídas privadas, posse de buffers, allocator original,
    proteção dos slots LCD e reconstrução de heap. Testes simulados passaram,
    mas console não mostrou popup. Esta candidata NÃO é baseline funcional.
11. Telemetria AST2/RPD5 precisou de coleta mais longa. Dados físicos: 4332
    apresentações, duas origens com 2166 amostras cada: 0x1f337940 e 0x1f36fd50.
    Segundo endereço alinhado em 16 bytes era rejeitado pelo guard de 32 bytes
    da v7.1: exatamente a alternância que explicava flicker. v7.2 também registrou
    falha de alocação/validação do pool; nenhum frame composto.
12. v7.3 voltou à composição que era visível. Alinha somente intervalo interior
    de cache do HUD: offsets conservadores [58212,224616), arredondados a 32.
    Invalidate/clean cobrem cada byte alterado, sem alcançar headers dos buffers.
    Mantém formato/stride/faixa e apresentação original. Nenhum pool VRAM extra.
13. Usuário confirmou resultado físico positivo descrito acima. Preservar v7.3.

## Testes e evidências

- Build limpa Wi-Fi 0 e 2; entrega com rede; ABI e espelho IGM 3968 bytes.
- Suíte host: parser streaming, cache, identidade, sessão, ledger, submissão,
  fila persistente com 210 pontos de erro/interrupção, política e preview.
- Bridge: CRC corrompido, FIFO, dedup, timeout, overflow, Unicode, slot isolado.
- ARM7 compilado no Unicorn: ordem serial, ACK, índices altos, barramento/cartão
  ocupados, peer estranho, preservação de pinos/RCNT/ABI e loops limitados.
- ARM11 compilado: nomes, fila, duração, rolagem, bounds, cache e publicação LCD.
- v7.3 testada com os DOIS endereços medidos, headers sentinela e cobertura de
  todos os bytes alterados. Caller/publicação originais executados no modelo.
- Corrigido teste bridge que estava após exit na suíte: antes passava apenas
  isoladamente. Gate movido antes do exit; suíte completa repetida e aprovada.
- Leitor RPD2/3/4/5 valida ELF, artefato e offset antes de acessar rede.
- FTP: backup local/remoto, staging/readback, promoção conjunta, rollback testado.
  Instalações persistentes passaram por autorização explícita quando exigida.
- Modelos não emulam GPU, cache, MMIO e timing reais. Sucesso físico é relato
  separado do usuário, vinculado por hashes lidos novamente no console.

## Baseline exata

TwlBg SHA256: acf9dd3cb0b11f0fcbf6dac3449a056b4f1cb2a782821a0a5fd69c9422209f5f
Bootstrap SHA256: 5a317d7db85dd470b93c08d8f674bd8ea8b8ff5662956a77e3b2b3a83740d66d

Sem novos benchmarks físicos numéricos na sessão final: diagnóstico salvo não
estava atualizado após Advance Wars. Não inventar p50/p95 ou confirmação remota.
Firmware original/derivado, ROMs, saves e credenciais não pertencem ao GitHub.

## Recursos e viabilidade

| Recurso | Avaliação |
|---|---|
| Temas, posição, duração, tamanho e opções por jogo | Viável; respeitar orçamento/área de cache |
| Pontos, descrição curta e modo efetivo no popup | Viável; ampliar evento com versão e limites |
| Lista de conquistas e progresso local | Viável; já há viewer/ledger; memória limita texto/cache |
| Badges offline pré-carregados | Viável com orçamento; não presumir catálogo inteiro na AXI |
| Progress notifications | Viável por eventos limitados e dedup; evitar spam e custo por frame |
| Fonte Unicode mais ampla | Viável com atlas/subconjunto; cobertura total custa memória |
| Menos latência RTC | Possível, requer medição e protocolo em blocos; não aumentar IRQ sem orçamento |
| Instalação assistida gerando patch local | Recomendado; gate por hash e backup obrigatório |
| Mais firmwares/modelos | Pesquisa por versão, mapas/ABI e testes físicos; não universal por assinatura |
| Internet durante gameplay | Pesquisa difícil; Wi-Fi/IRQ e jogos competem. Não prometer transporte nativo 3DS no TWL |
| Hardcore oficialmente confiável | Depende políticas e integração RA; não basta exibir rótulo |
| Integração oficial RA/certificação | Depende coordenação externa; testes locais não concedem aprovação |
| Ler RAM DS diretamente no ARM11 | Não presumir; mapeamentos atuais não oferecem esse contrato |
| Suporte universal DS/DSi/3DS ou todo jogo | Não demonstrado; ARM11/TwlBg é específico do 3DS |

Prioridade: matriz de regressão (MKDS, 1:1, sleep, segundo jogo, offline), medir
latência/tempo, UX de erro/partial coverage, depois badges/temas/progresso.

## GitHub e upstream

Recomendação: fork do **nds-bootstrap**, mais fontes do patch ARM11 em diretório
separado, sem redistribuir TwlBg.cxi. O núcleo modificado é nds-bootstrap;
TWiLight Menu++ é frontend e pode receber futuramente configurações/UX específicas.
Fork e PR não são alternativas exclusivas: desenvolver no fork, preparar PRs
pequenos para os repositórios responsáveis e discutir arquitetura antes do PR
monolítico. Não há garantia de aceitação upstream.

Fontes: https://github.com/DS-Homebrew/nds-bootstrap e
https://github.com/DS-Homebrew/TWiLightMenu .

Primeiros PRs candidatos: correções independentes de parser/testes/ABI; depois
bridge opt-in com orçamento e compatibilidade demonstrada. Integração de menus
no TWiLight merece PR separado somente se esse frontend for alterado.
