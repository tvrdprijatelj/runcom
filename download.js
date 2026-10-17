"use strict";
const sv = document.documentElement.lang === 'sv';
const text = (a,b) => sv ? a : b;
const os = document.getElementById('os');
const version = document.getElementById('version');
const status = document.getElementById('status');
const prerequisites = {
  arch:'sudo pacman -Syu --needed python tk curl',
  ubuntu:'sudo apt update && sudo apt install python3 python3-venv python3-tk curl',
  fedora:'sudo dnf install python3 python3-tkinter python3-pip curl',
  mac:text('Installera Python med Tcl/Tk från https://www.python.org/downloads/macos/', 'Install Python with Tcl/Tk from https://www.python.org/downloads/macos/'),
  windows:text('Installera Python från https://www.python.org/downloads/windows/ — välj Tcl/Tk och Python launcher.', 'Install Python from https://www.python.org/downloads/windows/ — include Tcl/Tk and Python launcher.'),
  linux:text('Installera Python 3.8+, Tkinter, venv och curl via din pakethanterare.', 'Install Python 3.8+, Tkinter, venv and curl using your package manager.')
};
function updateOS(){
  const win = os.value === 'windows';
  const main = version.value === 'main';
  document.getElementById('prerequisites').textContent = prerequisites[os.value];
  const base = 'https://raw.githubusercontent.com/tvrdprijatelj/runcom/main/';
  document.getElementById('command').textContent = win
    ? `Invoke-WebRequest -UseBasicParsing '${base}install.ps1' -OutFile runcom-install.ps1\npowershell -ExecutionPolicy Bypass -File .\\runcom-install.ps1${main ? ' -Ref main' : ''} -Language ${sv ? 'sv' : 'en'}`
    : `curl -fL '${base}install.sh' -o runcom-install.sh\nbash runcom-install.sh${main ? ' --ref main' : ''} --lang ${sv ? 'sv' : 'en'}`;
  const link = document.getElementById('installer');
  link.href = `install_${sv ? 'sv' : 'en'}.${win ? 'ps1' : 'sh'}`;
  link.textContent = text('Ladda ner installationsskript', 'Download installer');
  link.download = win ? 'runcom-install.ps1' : 'runcom-install.sh';
  document.getElementById('launch').textContent = win
    ? text('Sök efter Runcom i Start-menyn eller använd skrivbordsgenvägen. Installationen visar också ett startkommando.', 'Find Runcom in the Start menu or use the desktop shortcut. The installer also prints a launch command.')
    : text('Linux: sök efter Runcom i programmenyn. Installationen visar även startkommandot. Standardplats: ~/.local/share/runcom/runcom.', 'Linux: find Runcom in the application menu. The installer also prints a launch command. Default location: ~/.local/share/runcom/runcom.');
  status.textContent = main
    ? text('Valt: aktuell källkod på main, inklusive de nya rättningarna.', 'Selected: current source on main, including the latest fixes.')
    : text('Valt: senaste publicerade release. Den kan vara äldre än rättningarna på main.', 'Selected: latest published release. It may predate fixes on main.');
}
const platform = navigator.userAgentData?.platform || navigator.platform || '';
os.value = /Win/i.test(platform) ? 'windows' : /Mac/i.test(platform) ? 'mac' : 'linux';
os.addEventListener('change', updateOS);
version.addEventListener('change', updateOS);
updateOS();
document.getElementById('copy').addEventListener('click', async()=>{
  try {
    await navigator.clipboard.writeText(document.getElementById('command').textContent);
    status.textContent = text('Kommandona kopierades.', 'Commands copied.');
  } catch {
    status.textContent = text('Markera och kopiera kommandona manuellt.', 'Select and copy the commands manually.');
  }
});

const uninstallOS = document.getElementById('uninstall-os');
uninstallOS.value = /Win/i.test(platform) ? 'windows' : /Mac/i.test(platform) ? 'mac' : 'linux';
const uninstallDistros = {
  arch: {name:'Arch Linux / EndeavourOS / Manjaro', tools:'sudo pacman -Syu --needed python bash curl', menu:text('Ofta KDE eller GNOME: öppna programstartaren och sök efter Avinstallera Runcom (Uninstall Runcom).','Often KDE or GNOME: open the application launcher and search for Uninstall Runcom (Avinstallera Runcom).')},
  ubuntu: {name:'Ubuntu', tools:'sudo apt update && sudo apt install python3 bash curl', menu:text('I Ubuntu med GNOME: tryck Super, sök efter Avinstallera Runcom (Uninstall Runcom) och öppna träffen.','On Ubuntu with GNOME: press Super, search for Uninstall Runcom and open the result.')},
  debian: {name:'Debian', tools:'sudo apt update && sudo apt install python3 bash curl', menu:text('Öppna programmenyn i GNOME, KDE eller Xfce och sök efter Avinstallera Runcom (Uninstall Runcom).','Open the application menu in GNOME, KDE or Xfce and search for Uninstall Runcom.')},
  mint: {name:'Linux Mint', tools:'sudo apt update && sudo apt install python3 bash curl', menu:text('I Cinnamon: öppna Meny och sök efter Avinstallera Runcom (Uninstall Runcom). I MATE eller Xfce använder du motsvarande programmeny.','In Cinnamon: open Menu and search for Uninstall Runcom. In MATE or Xfce use the corresponding application menu.')},
  fedora: {name:'Fedora', tools:'sudo dnf install python3 bash curl', menu:text('I Fedora Workstation med GNOME: tryck Super och sök efter Avinstallera Runcom. I Fedora KDE använder du programstartaren.','In Fedora Workstation with GNOME: press Super and search for Uninstall Runcom. On Fedora KDE use the application launcher.')},
  opensuse: {name:'openSUSE', tools:'sudo zypper install python3 bash curl', menu:text('I KDE: öppna programstartaren och sök efter Avinstallera Runcom. I GNOME använder du översikten med Super.','In KDE: open the application launcher and search for Uninstall Runcom. In GNOME use the overview with Super.')},
  alpine: {name:'Alpine Linux', tools:'apk add python3 bash curl', menu:text('Om du använder ett grafiskt skrivbord: sök efter Avinstallera Runcom i dess programmeny. Utan skrivbord använder du terminalmetoden.','With a graphical desktop, search for Uninstall Runcom in its application menu. Without a desktop use the terminal method.')},
  linux: {name:text('Annan Linuxdistribution / osäker','Other Linux distribution / not sure'), tools:'python3 --version\nbash --version\ncurl --version', menu:text('Öppna din programmeny och sök efter Avinstallera Runcom (Uninstall Runcom). Saknas den använder du terminalmetoden.','Open your application menu and search for Uninstall Runcom. If it is missing, use the terminal method.')}
};
function updateUninstall(){
  const selected = uninstallOS.value;
  const win = selected === 'windows';
  const mac = selected === 'mac';
  const extension = win ? 'ps1' : 'sh';
  const link = document.getElementById('uninstaller');
  link.href = `uninstall.${extension}`;
  link.download = `runcom-uninstall.${extension}`;
  link.textContent = text('Ladda ner avinstallationsskript', 'Download uninstaller');
  const distro = uninstallDistros[selected] || uninstallDistros.linux;
  document.getElementById('uninstall-distro').textContent = win ? 'Windows' : mac ? 'macOS' : text('Instruktion för: ', 'Instructions for: ') + distro.name;
  document.getElementById('uninstall-menu').textContent = win
    ? text('Öppna Start-menyn, sök efter Avinstallera Runcom och starta genvägen.', 'Open Start, search for Avinstallera Runcom (Uninstall Runcom), and open the shortcut.')
    : mac ? text('I Finder: välj Gå → Gå till mapp och ange ~/.local/share/runcom. Öppna Uninstall Runcom.command. Använd din valda mapp om du installerade på en annan plats.', 'In Finder choose Go → Go to Folder and enter ~/.local/share/runcom. Open Uninstall Runcom.command. Use your chosen folder if you installed elsewhere.') : distro.menu;
  document.getElementById('uninstall-terminal').textContent = win
    ? text('Öppna PowerShell från Start-menyn. Stäng först Runcom.', 'Open PowerShell from Start. Close Runcom first.')
    : mac ? text('Öppna Terminal via Spotlight (Command+mellanslag, skriv Terminal). Stäng först Runcom.', 'Open Terminal using Spotlight (Command+Space, type Terminal). Close Runcom first.')
      : text('Öppna Terminal från programmenyn i ', 'Open Terminal from the application menu in ') + distro.name + text('. Stäng först Runcom.', '. Close Runcom first.');
  document.getElementById('uninstall-tools').textContent = win
    ? 'powershell -Command "$PSVersionTable.PSVersion"'
    : mac ? 'python3 --version\nbash --version\ncurl --version' : distro.tools;
  document.getElementById('uninstall-tools-note').textContent = win
    ? text('Windows-avinstalleraren använder PowerShell och behöver inte Python.', 'The Windows uninstaller uses PowerShell and does not need Python.')
    : mac ? text('På macOS behövs Python 3 för avinstalleraren. Om det saknas, installera Python från python.org. Bash och curl följer normalt med macOS.', 'On macOS the uninstaller needs Python 3. If missing, install Python from python.org. Bash and curl normally ship with macOS.')
      : selected === 'alpine' ? text('Kör följande i en root-terminal om verktygen saknas. Använd doas eller sudo om din Alpine-installation är konfigurerad för det.', 'Run the following in a root terminal if tools are missing. Use doas or sudo if configured on your Alpine installation.')
        : selected === 'linux' ? text('Kontrollera verktygen nedan. Saknas något, installera det med din distributions pakethanterare.', 'Check the tools below. If any are missing, install them with your distribution’s package manager.')
          : text('Om ett verktyg saknas, använd detta kommando för ', 'If a tool is missing, use this command for ') + distro.name + (selected === 'arch' ? text('. Kommandot gör även en fullständig systemuppdatering.', '. This also performs a full system upgrade.') : '.');
  const base = 'https://raw.githubusercontent.com/tvrdprijatelj/runcom/main/';
  document.getElementById('uninstall-command').textContent = win
    ? `Invoke-WebRequest -UseBasicParsing '${base}uninstall.ps1' -OutFile runcom-uninstall.ps1\npowershell -ExecutionPolicy Bypass -File .\\runcom-uninstall.ps1`
    : `curl -fL '${base}uninstall.sh' -o runcom-uninstall.sh\nbash runcom-uninstall.sh`;
  document.getElementById('uninstall-custom').textContent = win
    ? 'powershell -ExecutionPolicy Bypass -File .\\runcom-uninstall.ps1 -InstallDir "C:\\path\\to\\Runcom"'
    : 'RUNCOM_INSTALL_DIR="/path/to/runcom" bash runcom-uninstall.sh';
  document.getElementById('uninstall-status').textContent = '';
}
uninstallOS.addEventListener('change', updateUninstall);
updateUninstall();
document.getElementById('uninstall-copy').addEventListener('click', async()=>{
  const result = document.getElementById('uninstall-status');
  try {
    await navigator.clipboard.writeText(document.getElementById('uninstall-command').textContent);
    result.textContent = text('Kommandona kopierades.', 'Commands copied.');
  } catch {
    result.textContent = text('Markera och kopiera kommandona manuellt.', 'Select and copy the commands manually.');
  }
});
