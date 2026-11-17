# Voxa GEN 1.0.0

## Versão curta (GameBanana / itch.io)

Resumo de uma linha: Gera cromáticas de FNF a partir dos seus samples de voz, com marcadores para o Slicex.

Texto:

Voxa GEN pega uma pasta de samples de voz e devolve uma cromática afinada, com marcadores que o
Slicex do FL Studio usa para cortar uma nota por fatia.

Como usar:
1. Coloque os samples numa pasta, em WAV. Nomes como 1.wav, a.wav ou e2.wav são reconhecidos sozinhos.
2. Abra o VoxaGEN.exe e escolha essa pasta.
3. Escolha a primeira nota, a oitava e quantas notas quer.
4. Exporte e arraste o WAV da cromática para o Slicex.

Você escolhe entre três modos de afinação: Natural (mantém o timbre da voz), Robot e Legacy. O LAB
tem 14 efeitos opcionais para testar num sample antes de exportar, e o preview toca exatamente o
que vai para o arquivo. Também dá para salvar cada nota em um WAV separado.

Seus samples originais nunca são alterados, e uma exportação nunca apaga outra sem perguntar.

Windows 10/11, 64 bits. Não precisa instalar. Funciona sem internet.

Licença GPL-3.0: use como quiser; se redistribuir, siga a licença e inclua o código-fonte.
© 2026 Rambyte Team. Créditos completos dentro do app, em Configurações > Sobre.

## Versão completa (README / página do projeto)

Voxa GEN transforma samples de voz numa escala cromática pronta para usar. Você aponta uma pasta
com os seus WAVs (a.wav, e2.wav, 1.wav...), escolhe a primeira nota e quantas notas quer, e ele
afina cada uma no tom certo. Sai um WAV com todas as notas em sequência e marcadores que o Slicex
do FL Studio corta sozinho, e, se você quiser, um arquivo separado para cada nota.

Uma cromática é a mesma voz cantando cada semitom em sequência. Com ela, um sampler ou o Slicex
toca qualquer melodia com aquela voz, que é como se fazem covers e músicas de mods de FNF.

## Requisitos

Windows 10 ou 11, 64 bits. O download tem cerca de 112 MB. Não precisa instalar nada: descompacte
o .zip e abra o VoxaGEN.exe. Os samples precisam estar em WAV.

## Como usar no FL Studio

1. No Voxa GEN, escolha a pasta dos samples, a primeira nota e quantas notas quer.
2. Exporte. O app cria uma pasta com o WAV da cromática inteira e, se marcado, uma pasta com cada nota.
3. No FL Studio, abra o Slicex e arraste o WAV da cromática para dentro dele. Os marcadores já
   dividem o arquivo em uma fatia por nota.

## O que dá pra fazer

Há três jeitos de afinar. O Natural mantém o timbre da voz em qualquer altura, sem efeito de
esquilo nas notas agudas nem de gigante nas graves. O Robot deixa a voz reta, com som de máquina.
O Legacy segue a cadeia clássica dos geradores de cromática antigos.

No LAB você testa um sample de cada vez antes de exportar tudo. São 14 efeitos (distorção,
vibrato, chorus, ring modulator, EQ e outros) que podem ser encadeados, com comparação antes e
depois. Os efeitos vêm desligados e só entram na exportação se você ligar.

O preview usa o mesmo processamento da exportação, então o que você ouve é o que vai para o
arquivo. Também dá para salvar o trabalho como projeto (.vxproj), colocar várias exportações numa
fila e pedir para o app procurar problemas nos samples antes de exportar, como arquivo faltando,
silêncio, clipping e volume desigual.

Cada configuração tem um botão "?" que explica o que ela faz e por que usar. A interface está em
inglês, português (Brasil e Portugal), português com gírias, espanhol, japonês, Pirate English e
Meowgwenge, o inglês de gato. Cores, fonte, tamanho do texto e cantos podem ser mudados à vontade.

## Promessas

Estas valem para a versão 1.0.0 e são verificadas pelos testes automáticos do projeto.

- O Voxa GEN nunca altera os seus samples originais. Ele só lê esses arquivos.
- Nenhuma exportação apaga outra sem perguntar. Na fila em lote, ele cria uma pasta numerada nova
  em vez de sobrescrever.
- Se uma exportação falhar ou for cancelada, não fica arquivo pela metade na pasta de destino.
- Antes de entregar uma exportação, o app confere os arquivos escritos: cabeçalho, duração,
  marcadores e conteúdo. Se algo não bater, ele avisa em vez de dizer que deu certo.
- As notas saem afinadas com erro abaixo de 5 cents nos testes do projeto.
- O app funciona sem internet e não envia dados para lugar nenhum.
- É gratuito e de código aberto, sob a licença GPL-3.0.

## Versões

1.0.0: primeira versão pública.

## Licença e créditos

© 2026 Rambyte Team. Software livre sob a GNU General Public License, versão 3 ou posterior. Vem
sem garantia.

Os sons da interface são os charting sounds de Friday Night Funkin', da The Funkin' Crew Inc.,
usados com crédito. As fontes são Inter, de Rasmus Andersson (SIL OFL 1.1), e VCR OSD Mono, de
Riciery Leal, usada com crédito. A análise de voz usa WORLD, de Masanori Morise, e Praat, de Paul
Boersma e David Weenink, por meio do Parselmouth. A lista completa está em docs/LICENSES.md.
