# Teste nativo ARM11

Homebrew isolado para verificar orientação, aparência, expiração e custo do
compositor em CPU ARM11 real. Mostra quatro capturas do Mario Kart DS; não
executa o jogo, avalia conquistas ou integra TwlBg. Não substitui bootstrap,
firmware, configuração ou save.

## Estado em 29/10/2026

Primeira build executada sofreu data abort ao copiar para framebuffer em
VRAM. Dump foi vinculado ao ELF preservado por correspondência exata dos
96 bytes de código e pela cadeia `main -> ra_postcompose -> memcpy`.
Escrita em `0x1f300008` falhou por permissão, dentro do destino de 288000
bytes. Esse resultado descreve o processo homebrew; não estabelece as
permissões do TwlBg.

Correção usa framebuffers em linear RAM, como `gfxInitDefault`, e consulta
permissão de leitura/escrita de toda a faixa antes de desenhar. Uma superfície
negada encerra desenho e registra `render_error=-4`, sem tentar escrever uma
tela de erro no mesmo buffer.

Build corrigida copiada, relida no SD e executada com sucesso:

- Pasta: `/3ds/ra-arm11-test/`.
- SHA256 `.3dsx`: `b85e1bfe89884295eb86d2ae470e21c31665ddd5acf1e484e8268a29ff9fb4a3`.
- Pacote/ELF privado: `ra-overlay-research-20261029/arm11-test-build-v5/`.
- Primeira build preservada em `arm11-test-build-v2/`; backup remoto tem sufixo
  `.before-ram-fix`. Esse backup contém a versão que sofreu crash.
- Evidências: `docs/research/20261029/arm11-native-test/`.

Relatório `/3ds/ra-arm11-test/reports/000/` adquirido após usuário informar
“funcionou. salvei o log.” Evidência em
`docs/research/20261029/arm11-native-test/console-test-000.json`:

- 3333 quadros em 55,706 segundos: média de 59,83 quadros enviados/s.
- `render_error=0`, quatro verificações de permissão, nenhuma suspensão.
- Oito previews e nove trocas de tela; seis popups expiraram após 180 quadros
  (cerca de 3,008 segundos de parede); três foram substituídos por novo pedido.
- Cópia das duas telas mais popup: média 5354 us, máximo 6257 us,
  p95 recente 5467 us. Cache: média 264 us, máximo 444 us.
- Último quadro salvo, já sem popup, comparado à captura fonte correta:
  zero diferenças nos 164608 pixels fora dos dois rodapés do teste.

Isso confirma funcionamento deste aplicativo e limpeza no último quadro
salvo. Não há captura de todos os quadros para certificar ausência de tearing
ou resíduos transitórios. Custos incluem cópia integral das duas telas;
não isolam custo do texto nem estabelecem orçamento de CPU do TwlBg.
Capturas e relatório bruto preservados na pasta privada
`ra-overlay-research-20261029/arm11-native-report-000/`.

## Uso no console

Abra **RA ARM11 Test** no Homebrew Launcher. Popup inicial dura 180 quadros;
captura de fundo muda a cada 90 quadros.

- **A**: novo popup sintético.
- **X**: alterna tela física do popup.
- **B**: fecha popup.
- **START**: salva relatório e últimas imagens, depois retorna ao launcher.

Saída em `/3ds/ra-arm11-test/reports/NNN/`: `report.json`, `top.bgr`
(288000 bytes) e `bottom.bgr` (230400 bytes). Imagens são BGR com rotação
nativa: pixel `(x,y)` começa em `(x*240+239-y)*3`.

## Build e verificação

Execute da raiz do repositório, usando diretório de saída novo:

```sh
rtk proxy python3 -B tools/ra_arm11_test/build.py \
  /path/to/projects/ra-overlay-research-20261029 \
  /path/to/projects/ra-overlay-research-20261029/arm11-test-build-NOVO
rtk proxy python3 -B tools/ra_arm11_test/test_app.py \
  /path/to/projects/ra-overlay-research-20261029/arm11-test-build-v5/frames.bin
```

Build usa devkitARM/libctru, rasterizador de texto de produção e compositor
experimental. Capturas e binários permanecem na pasta privada, fora do Git.

Modelo host passou 450 quadros, 900 comparações de painéis, canários,
expiração/controles e ASan/UBSan. Caso negativo usa mapeamento protegido
somente leitura e confirma rejeição antes da primeira cópia. Esses testes
não certificam libctru, apresentação nem timing no console.

## Leitura das medidas

`copy_and_popup_us` inclui cópia integral dos dois painéis e popup; exclui
rodapés e gravação SD. `flush_us` mede limpeza de cache separadamente.
Médias/máximos cobrem sessão; percentis cobrem últimas 600 amostras.
`drawn_frames` conta quadros enviados pelo aplicativo; não mede duração
fotométrica. Suspensões afetam duração de parede. Frequência real da CPU
não é medida.

Mesmo se aprovado, teste não comprova propriedade de buffers, sincronização,
transporte ARM7/ARM11 ou integração em TwlBg durante jogo DS. Essas etapas
continuam pendentes.
