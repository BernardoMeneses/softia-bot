const INVITE_URL = "https://discord.com/oauth2/authorize?client_id=1517642102773780680";
const CONTACT_EMAIL = "bernardojvmeneses@gmail.com";
const DEFAULT_ROUTE = "#home";
const DEFAULT_LANGUAGE = "pt";

const TRANSLATIONS = {
  pt: {
    pageTitle: "Softia | Discord Bot",
    pageDescription:
      "Adiciona a Softia ao teu servidor Discord para musica, jogos, economia, eventos e moderacao.",
    "nav.label": "Navegacao principal",
    "nav.features": "Funcionalidades",
    "nav.commands": "Comandos",
    "nav.contact": "Contacto",
    "nav.invite": "Convidar",
    "nav.add": "Convidar",
    "language.label": "Idioma",
    "hero.eyebrow": "Discord bot",
    "hero.title": "A Softia no teu servidor.",
    "hero.lead":
      "Um bot com musica, jogos, economia, eventos e moderacao, preparado para comunidades que querem comandos rapidos e uma presenca visual propria.",
    "hero.summaryLabel": "Resumo",
    "hero.statMusic": "Spotify e YouTube",
    "hero.statGames": "Blackjack e economia",
    "hero.statEvents": "Eventos e moderacao",
    "actions.addDiscord": "Convidar para o Discord",
    "actions.copyLink": "Copiar link",
    "actions.linkCopied": "Link copiado",
    "bot.cardLabel": "Perfil da Softia",
    "bot.avatarAlt": "Imagem de perfil da Softia",
    "bot.role": "Musica, jogos e comunidade",
    "bot.nowPlaying": "A tocar agora",
    "bot.favoriteSong": "A tua musica favorita",
    "features.eyebrow": "Funcionalidades",
    "features.title": "O essencial para manter o servidor ativo.",
    "features.musicTitle": "Musica",
    "features.musicText": "YouTube, Spotify por pesquisa, queue, loop, skip, stop e disconnect.",
    "features.gamesTitle": "Jogos",
    "features.gamesText": "Blackjack com alias -bj, apostas, carteira e estado persistente.",
    "features.eventsTitle": "Eventos",
    "features.eventsText": "Eventos interativos para votacoes, quizzes, corridas e recompensas.",
    "features.moderationTitle": "Moderacao",
    "features.moderationText": "Ferramentas para bans, kicks, limpeza de mensagens e protecao anti-spam.",
    "commands.eyebrow": "Comandos",
    "commands.title": "Prefixo rapido, sem setup pesado.",
    "commands.mainLabel": "Comando principal",
    "commands.infoText":
      "Abre o painel visual da Softia e da acesso rapido as categorias de comandos do bot.",
    "commands.music": "Musica",
    "commands.games": "Jogos",
    "commands.server": "Servidor",
    "contact.eyebrow": "Contacto",
    "contact.title": "Problemas com a Softia?",
    "contact.text":
      "Se o bot nao responder, falhar musica ou faltar alguma permissao, envia os detalhes para o suporte.",
    "contact.supportTitle": "Suporte AllSoftSystems",
    "contact.supportText":
      "Inclui o nome do servidor, o comando usado e a mensagem de erro que apareceu no Discord.",
    "contact.emailAction": "Enviar email",
    "contact.beforeTitle": "Antes de contactar",
    "contact.checkInfo": "Usa -info para confirmar os comandos disponiveis.",
    "contact.checkVoice": "Confirma que a Softia tem acesso ao canal de voz/texto.",
    "contact.checkError": "Guarda o erro exato mostrado pelo bot.",
    "invite.eyebrow": "Convidar",
    "invite.title": "Leva a Softia para o teu servidor.",
    "invite.text":
      "O convite abre diretamente no Discord. Escolhe o servidor, confirma as permissoes e a Softia fica pronta para receber comandos.",
    
    "footer.rights": "Todos os direitos reservados.",
    "footer.top": "Voltar ao topo",
    "status.copyError": "Nao consegui copiar automaticamente. Abre o convite pelo botao principal.",
  },
  en: {
    pageTitle: "Softia | Discord Bot",
    pageDescription:
      "Add Softia to your Discord server for music, games, economy, events, and moderation.",
    "nav.label": "Main navigation",
    "nav.features": "Features",
    "nav.commands": "Commands",
    "nav.contact": "Contact",
    "nav.invite": "Invite",
    "nav.add": "Invite",
    "language.label": "Language",
    "hero.eyebrow": "Discord bot",
    "hero.title": "Softia for your server.",
    "hero.lead":
      "A bot with music, games, economy, events, and moderation, built for communities that want fast commands and a distinct visual presence.",
    "hero.summaryLabel": "Summary",
    "hero.statMusic": "Spotify and YouTube",
    "hero.statGames": "Blackjack and economy",
    "hero.statEvents": "Events and moderation",
    "actions.addDiscord": "Invite to Discord",
    "actions.copyLink": "Copy link",
    "actions.linkCopied": "Link copied",
    "bot.cardLabel": "Softia profile",
    "bot.avatarAlt": "Softia profile image",
    "bot.role": "Music, games, and community",
    "bot.nowPlaying": "Now playing",
    "bot.favoriteSong": "Your favorite song",
    "features.eyebrow": "Features",
    "features.title": "Everything needed to keep the server active.",
    "features.musicTitle": "Music",
    "features.musicText": "YouTube, Spotify via search, queue, loop, skip, stop, and disconnect.",
    "features.gamesTitle": "Games",
    "features.gamesText": "Blackjack with -bj alias, bets, wallet, and persistent state.",
    "features.eventsTitle": "Events",
    "features.eventsText": "Interactive events for votes, quizzes, races, and rewards.",
    "features.moderationTitle": "Moderation",
    "features.moderationText": "Tools for bans, kicks, message cleanup, and anti-spam protection.",
    "commands.eyebrow": "Commands",
    "commands.title": "Fast prefix commands, no heavy setup.",
    "commands.mainLabel": "Main command",
    "commands.infoText":
      "Opens Softia's visual panel and gives quick access to the bot's command categories.",
    "commands.music": "Music",
    "commands.games": "Games",
    "commands.server": "Server",
    "contact.eyebrow": "Contact",
    "contact.title": "Having trouble with Softia?",
    "contact.text":
      "If the bot does not respond, music fails, or a permission is missing, send the details to support.",
    "contact.supportTitle": "AllSoftSystems support",
    "contact.supportText": "Include the server name, the command used, and the error message shown in Discord.",
    "contact.emailAction": "Send email",
    "contact.beforeTitle": "Before contacting",
    "contact.checkInfo": "Use -info to confirm the available commands.",
    "contact.checkVoice": "Confirm Softia has access to the voice/text channel.",
    "contact.checkError": "Save the exact error shown by the bot.",
    "invite.eyebrow": "Invite",
    "invite.title": "Bring Softia to your server.",
    "invite.text":
      "The invite opens directly in Discord. Choose the server, confirm the permissions, and Softia is ready to receive commands.",
    "invite.status": "Official Softia link ready.",
    "footer.rights": "All rights reserved.",
    "footer.top": "Back to top",
    "status.copySuccess": "Official Softia link copied.",
    "status.copyError": "Could not copy automatically. Open the invite with the main button.",
  },
};

const inviteLinks = [...document.querySelectorAll("[data-invite-link]")];
const copyButtons = [...document.querySelectorAll("[data-copy-invite]")];
const statusBoxes = [...document.querySelectorAll("[data-copy-status]")];
const contactEmailLinks = [...document.querySelectorAll("[data-contact-email]")];
const routeLinks = [...document.querySelectorAll("[data-route]")];
const languageButtons = [...document.querySelectorAll("[data-language]")];
const yearTargets = [...document.querySelectorAll("[data-year]")];
const metaDescription = document.querySelector('meta[name="description"]');
const routeIds = routeLinks
  .map((link) => link.getAttribute("href"))
  .filter((href) => href && href.startsWith("#"));

let currentLanguage = storedLanguage();
let copyResetTimer = null;

inviteLinks.forEach((link) => {
  link.href = INVITE_URL;
});

contactEmailLinks.forEach((link) => {
  link.href = `mailto:${CONTACT_EMAIL}?subject=Softia%20support`;
});

yearTargets.forEach((target) => {
  target.textContent = new Date().getFullYear().toString();
});

function storedLanguage() {
  const savedLanguage = readStorage("softiaLanguage");
  if (TRANSLATIONS[savedLanguage]) return savedLanguage;

  const browserLanguage = navigator.language?.toLowerCase() || "";
  return browserLanguage.startsWith("en") ? "en" : DEFAULT_LANGUAGE;
}

function readStorage(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Language switching still works for the current page when storage is blocked.
  }
}

function t(key) {
  return TRANSLATIONS[currentLanguage][key] || TRANSLATIONS[DEFAULT_LANGUAGE][key] || key;
}

function applyLanguage(language) {
  currentLanguage = TRANSLATIONS[language] ? language : DEFAULT_LANGUAGE;
  writeStorage("softiaLanguage", currentLanguage);
  document.documentElement.lang = currentLanguage;
  document.title = t("pageTitle");

  if (metaDescription) {
    metaDescription.setAttribute("content", t("pageDescription"));
  }

  document.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });

  document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
    element.setAttribute("aria-label", t(element.dataset.i18nAriaLabel));
  });

  document.querySelectorAll("[data-i18n-alt]").forEach((element) => {
    element.setAttribute("alt", t(element.dataset.i18nAlt));
  });

  languageButtons.forEach((button) => {
    const isActive = button.dataset.language === currentLanguage;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });

  updateCopyButtons(false);
}

function validRoute(hash) {
  return routeIds.includes(hash) ? hash : DEFAULT_ROUTE;
}

function syncRoute() {
  const activeRoute = validRoute(window.location.hash || DEFAULT_ROUTE);
  if (window.location.hash !== activeRoute) {
    history.replaceState(null, "", activeRoute);
  }

  routeLinks.forEach((link) => {
    const isActive = link.getAttribute("href") === activeRoute;
    link.classList.toggle("active", isActive);
    if (isActive) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  });
}

function setStatus(message, type = "ready") {
  statusBoxes.forEach((box) => {
    box.classList.remove("ready", "error");
    box.classList.add(type);
    box.textContent = message;
  });
}

function renderIcons() {
  if (window.lucide) {
    window.lucide.createIcons();
  }
}

function updateCopyButtons(isCopied) {
  copyButtons.forEach((button) => {
    const icon = button.querySelector("[data-lucide]");
    const label = button.querySelector("[data-i18n='actions.copyLink']");

    if (icon) {
      icon.setAttribute("data-lucide", isCopied ? "check" : "copy");
    }

    if (label) {
      label.textContent = t(isCopied ? "actions.linkCopied" : "actions.copyLink");
    }

    button.classList.toggle("copied", isCopied);
  });

  renderIcons();
}

async function copyInvite() {
  try {
    await navigator.clipboard.writeText(INVITE_URL);
    setStatus(t("actions.linkCopied"));
    updateCopyButtons(true);
    clearTimeout(copyResetTimer);
    copyResetTimer = setTimeout(() => updateCopyButtons(false), 2200);
  } catch {
    setStatus(t("status.copyError"), "error");
  }
}

languageButtons.forEach((button) => {
  button.addEventListener("click", () => applyLanguage(button.dataset.language));
});

copyButtons.forEach((button) => {
  button.addEventListener("click", copyInvite);
});

window.addEventListener("hashchange", syncRoute);
applyLanguage(currentLanguage);
syncRoute();

renderIcons();
