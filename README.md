# RetroAchievements para nds-bootstrap — v7.3 experimental

[Baixe a primeira versão em Releases](https://github.com/1weell/nds-bootstrap/releases).

O ZIP da release inclui o bootstrap compilado, configuração sem dados pessoais, coletor
para Homebrew Launcher e um gerador local do módulo de popup. A versão original
v7.3 teve popup estável e conquistas relatadas no Kirby e identificação no Advance
Wars em um console. Em 01/11/2026, a pessoa responsável pelo teste instalou o
bootstrap recompilado deste pacote e relatou que tudo funcionou perfeitamente no
teste solicitado com Kirby, incluindo nome na abertura e popups de conquistas.
Este relato não comprova compatibilidade com todos os modelos ou jogos, nem
confirmação de conquistas pelo servidor.

## Antes de começar

Você precisa de um 3DS/2DS com Luma3DS, Homebrew Launcher, TWiLight Menu++ e
nds-bootstrap já funcionando, um computador com Python 3 e um cartão SD acessível.
O jogo precisa ser identificado e ter conquistas disponíveis no RetroAchievements.
Use cópias de jogos obtidas de forma apropriada. Este pacote não inclui jogos.

O módulo de popup contém partes do firmware Nintendo e, por isso, **não vem no
ZIP**. Você precisa gerá-lo no seu computador usando o firmware do seu console.
O gerador aceita apenas o TWL_FIRM com SHA-256
`403580f164a346066d8d4d0e33baf50362821fe54164272a34d7593e7c766197`.
Outras revisões serão recusadas; não force o processo nem baixe firmware de terceiros.

Faça backup dos seguintes arquivos se já existirem, incluindo sua configuração:

- `sd:/_nds/nds-bootstrap-release.nds`
- `sd:/_nds/nds-bootstrap/ra.cfg`
- `sd:/luma/sysmodules/TwlBg.cxi`

Se já usa um TwlBg personalizado (por exemplo, por outro patch), este módulo o
substituirá; compatibilidade entre patches não foi verificada.

## 1. Obter seu firmware localmente

1. Copie `sd/3ds/ra-twlbg-dump/` deste pacote para `sd:/3ds/`.
2. No console, abra Homebrew Launcher e execute **RA TwlBg Dump**. A ferramenta
   lê o TWL_FIRM instalado e salva em uma nova pasta numerada dentro de
   `sd:/3ds/ra-twlbg-dump/dumps/`. Ela não altera a NAND.
3. Ao terminar, pressione START. No computador, localize o arquivo `twl.firm`
   da pasta criada. Se houver erro de leitura, o módulo não poderá ser gerado.
4. Guarde o dump apenas em local privado. Não envie o arquivo nem publique a pasta.

O coletor foi compilado e passou nos testes automatizados de leitura; esta build
específica não recebeu teste independente em outro console.

## 2. Gerar o módulo de popup

Abra um terminal na pasta deste pacote. Exemplos; substitua os caminhos pelos seus:

```sh
python3 gerador/gerar_twlbg.py /caminho/privado/twl.firm /caminho/privado/saida
```

No Windows, use `py -3` no lugar de `python3` e caminhos entre aspas se tiverem
espaços. O comando valida o firmware e deve gerar `TwlBg.cxi` na pasta de saída.
A saída também contém cópias de firmware: mantenha toda a pasta privada. Se o hash
não for aceito, pare: esta versão ainda não suporta essa imagem.

## 3. Instalar

1. Desligue o console e faça os backups descritos acima.
2. Copie o conteúdo da pasta `sd/` para a raiz do cartão SD. O bootstrap vai para
   `sd:/_nds/nds-bootstrap-release.nds` e o exemplo para
   `sd:/_nds/nds-bootstrap/ra.cfg`. **Se já usa RA, preserve seu ra.cfg ou
   transfira suas preferências para o novo arquivo; a cópia pode sobrescrevê-lo.**
3. Copie o `TwlBg.cxi` que você gerou para `sd:/luma/sysmodules/TwlBg.cxi`.
   Crie a pasta se necessário. Nunca compartilhe esse arquivo.
4. Ative `Enable loading external FIRMs and modules` na configuração do Luma3DS
   (normalmente, segure SELECT ao ligar), salve e reinicie o console.
5. No TWiLight Menu++, selecione o nds-bootstrap de release e inicie o jogo.
   A configuração específica do TWiLight pode variar conforme sua versão.

## 4. Configurar sua conta e jogar

Abra `sd:/_nds/nds-bootstrap/ra.cfg` em um editor de texto. Preencha `username=`
e `password=` com sua conta RetroAchievements. O exemplo distribuído está vazio.
O arquivo guarda a senha em texto simples e o cliente a transmite por **HTTP sem
criptografia**. Qualquer pessoa ou equipamento que observe a rede pode capturá-la.
Use somente se aceitar esse risco; não envie seu `ra.cfg` a outras pessoas.

O exemplo usa `overlay=2` para tentar mostrar popups em jogos identificados,
`renderer=arm11`, `queue=1`, `sync=1`, `submit=1` e `hardcore=0`. Com
`overlay=1`, defina também os IDs em `overlay_games=`, separados por vírgulas;
`overlay=0` desliga os popups. `sync=0` depende de dados já salvos em cache.

Na abertura, uma conexão compatível é necessária para autenticar e obter os dados
do jogo; após isso, o jogo inicia. No jogo, use o menu de nds-bootstrap
(normalmente L + R + baixo + B) e procure RetroAchievements para diagnósticos e
preview. Popups de teste não concedem conquistas. Desbloqueios são guardados e
podem ser enviados em inicialização posterior; popup não comprova confirmação
pelo servidor. Para jogos DS, abra o menu ou saia normalmente para gravar a fila;
um desligamento abrupto pode perder eventos ainda em memória. Consulte sua conta
no RetroAchievements para verificar o resultado. Hardcore oficial não é garantido.

## 5. Restaurar

Desligue o console. Restaure seus backups nos caminhos originais. Se não havia um
TwlBg personalizado antes, remova `sd:/luma/sysmodules/TwlBg.cxi` para voltar ao
módulo padrão. Reinicie. Preserve dados e configurações que você queira manter.

## Conteúdo e código-fonte

- `sd/_nds/nds-bootstrap-release.nds`: bootstrap recompilado.
- `sd/_nds/nds-bootstrap/ra.cfg`: exemplo sem credenciais.
- `sd/3ds/ra-twlbg-dump/`: coletor 3DS compilado.
- `gerador/`: payload compilado e gerador local, sem firmware Nintendo.
- `fonte-coletor/`: fonte do coletor. Licença: `LICENSE`.
- Código do bootstrap e do payload: https://github.com/1weell/nds-bootstrap/tree/ra-v73-port

Leia `SHA256SUMS.txt` para conferir a integridade dos arquivos do pacote.

## Para desenvolvedores

A branch `ra-v73-port` deriva do nds-bootstrap oficial. Para compilar, inicialize
os submódulos e instale as dependências do devkitPro. Os testes e a build limpa
são executados a partir da raiz do repositório:

```sh
git submodule update --init --recursive
bash tools/ra_reader_test.sh
bash tools/ra_release.sh /caminho/privado/nds-bootstrap-release.nds
```

A build ARM11 a partir do código requer um dump de firmware privado e devkitARM;
veja [antigravity/README.md](antigravity/README.md). Não publique firmware,
CXI gerado, saves, ROMs ou `ra.cfg` preenchido. Para o histórico técnico e os
limites de validação, leia [o relatório](docs/RELATORIO_01-11-2026.md) e
[PORTING_V73.md](PORTING_V73.md).
