"use strict";
const sv = document.documentElement.lang === 'sv';
const text = (a,b) => sv ? a : b;
const os = document.getElementById('os');
const status = document.getElementById('status');
const prerequisites = {
arch:'sudo pacman -Syu --needed python tk curl',
ubuntu:'sudo apt update && sudo apt install python3 python3-venv python3-tk curl',
fedora:'sudo dnf install python3 python3-tkinter python3-pip curl',
mac:text('Installera Python med Tcl/Tk från https://www.python.org/downloads/macos/', 'Install Python with Tcl/Tk from https://www.python.org/downloads/macos/'),
windows:text('Installera Python från https://www.python.org/downloads/windows/ — välj Tcl/Tk och Python launcher.', 'Install Python from https://www.python.org/downloads/windows/ — include Tcl/Tk and Python launcher.'),
linux:text('Installera Python 3.8+, Tkinter, venv och curl via din pakethanterare.', 'Install Python 3.8+, Tkinter, venv and curl using your package manager.')};
function updateOS(){
 const win = os.value === 'windows';
 document.getElementById('prerequisites').textContent = prerequisites[os.value];
 document.getElementById('command').textContent = win ? 'powershell -ExecutionPolicy Bypass -File .\\install.ps1' : 'bash install.sh';
 const link = document.getElementById('installer');
 link.href = win ? 'install.ps1' : 'install.sh'; link.download = win ? 'install.ps1' : 'install.sh';
 document.getElementById('launch').textContent = win ? text('Starta sedan med genvägen Runcom på skrivbordet.', 'Then launch Runcom using the desktop shortcut.') : text('Installationen visar kommandot för att starta Runcom. Standardplats: ~/.local/share/runcom/runcom.', 'The installer prints the launch command. Default location: ~/.local/share/runcom/runcom.');
 status.textContent = '';
}
const platform = navigator.platform || '';
os.value = /Win/i.test(platform) ? 'windows' : /Mac/i.test(platform) ? 'mac' : 'linux';
os.addEventListener('change',updateOS); updateOS();
document.getElementById('copy').addEventListener('click',async()=>{
 try { await navigator.clipboard.writeText(document.getElementById('command').textContent); status.textContent = text('Kommandot kopierades.', 'Command copied.'); }
 catch { status.textContent = text('Markera och kopiera kommandot manuellt.', 'Select and copy the command manually.'); }
});
