# Softia Bot

Softia e uma assistente pessoal que para já apenas um bot de discord mas terá outras integrações em automação de tarefas futuramente.

## Comandos

### Info

- `-devs` - mostra os criadores do bot
- `-sum` - apresenta o bot
- `-info` - mostra comandos de info

### Musica

- `-musicinfo` - mostra comandos de musica
- `-play <link ou nome>` - toca YouTube, procura pelo nome ou resolve link Spotify por pesquisa
- `-loop` - liga/desliga loop da musica atual
- `-next` - passa para a proxima musica da queue
- `-back` - volta para a musica anterior
- `-queue` - mostra a queue atual

Links Spotify sao resolvidos por titulo e pesquisados no YouTube, porque o bot nao faz streaming direto do Spotify.

### Math

- `-mathinfo` - mostra comandos de matematica
- `-sum <num1> <num2>` - soma
- `-sub <num1> <num2>` - subtracao
- `-mult <num1> * <num2>` - multiplicacao
- `-div <num1> / <num2>` - divisao
- `-mod <num1> % <num2>` - modulo
- `-pow <num1> ^ <num2>` - potencia
- `-sqrt <num> [grau]` - raiz quadrada, cubica ou de grau x
- `-matrix [[1,2],[3,4]] * [[5,6],[7,8]]` - multiplicacao de matrizes

### Search

- `-searchinfo` - mostra comandos de pesquisa
- `-grepg <texto>` - devolve os primeiros 5 resultados do Google
- `-grepb <texto>` - devolve os primeiros 5 resultados do Bing

Quando o HTML do motor de pesquisa bloqueia resultados diretos, o bot usa um fallback de pesquisa para continuar a devolver links.

### Conversas

- `-chatinfo` - mostra comandos de conversa
- `-chat <prompt>` - inicia uma conversa com IA usando a API do OpenAI
- `-abortchat` - termina o modo chat e envia um `.txt` com a conversa

No modo chat, as mensagens seguintes do utilizador no mesmo canal passam a ser interpretadas como prompts ate ser usado `-abortchat`.

### Gestao de Servidor

- `-serverinfo` - mostra comandos de gestao do servidor
- `-clear <quantidade>` - apaga 1 a 100 mensagens do canal atual
- `-kick @membro [motivo]` - expulsa um membro do servidor
- `-ban @membro [motivo]` - bane um membro do servidor

Os comandos de moderacao exigem as permissoes equivalentes no Discord, tanto no utilizador como no bot.

### Eventos Aleatorios

- `-eventsinfo` - mostra comandos de eventos aleatorios
- `-seteventchannel #canal` - define o chat onde os eventos aparecem
- `-eventson` - ativa eventos aleatorios automaticos
- `-eventsoff` - desativa eventos aleatorios automaticos
- `-eventnow` - envia um evento aleatorio imediatamente

Os eventos automaticos usam o canal definido por `-seteventchannel` ou por `EVENT_CHANNEL_ID`. Os eventos sao interativos, com botoes para votacoes, quizzes e escolhas rapidas. O bot roda a lista de eventos por servidor para evitar repetir o mesmo evento ate a lista ser usada.

### Auditoria Anti-Spam

- `-auditinfo` - mostra comandos de auditoria anti-spam
- `-auditon` - ativa auditoria anti-spam automatica
- `-auditoff` - desativa auditoria anti-spam automatica

A auditoria observa mensagens continuamente, apaga bursts de spam ou repeticao da mesma imagem em varios canais, e tenta banir automaticamente o responsavel. Membros com permissoes de moderacao ficam isentos para reduzir falsos positivos.

### Jogos e Economia

- `-gameinfo` - mostra comandos de jogos e economia
- `-wallet [@membro]` - mostra a carteira de moedas de um utilizador
- `-daily` - recebe moedas diarias
- `-shop` - mostra a loja de items
- `-buy <item_id> [quantidade]` - compra items com moedas
- `-inventory [@membro]` - mostra items comprados
- `-leaderboard` - mostra utilizadores com mais moedas
- `-blackjack <aposta>` - blackjack com botoes Hit/Stand
- `-coinflip <heads/tails> <aposta>` - moeda ao ar
- `-slots <aposta>` - slot machine
- `-dice <1-6> <aposta>` - aposta no resultado do dado

Cada utilizador comeca com uma wallet de moedas e o estado fica guardado em `data/game_state.json`.


O `Message Content Intent` do Discord e obrigatorio, porque o bot usa comandos com prefixo e le mensagens no modo chat.
