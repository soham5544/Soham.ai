// Hide loading animation after 2.5 sec
window.addEventListener('load', () => {
    setTimeout(() => {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.style.opacity = '0';
            overlay.style.transition = 'opacity 0.5s ease';
            setTimeout(() => overlay.remove(), 500);
        }
    }, 2500); // show for 2.5 seconds
});

// static/script.js
let currentGod = 'Krishna';
const chatBox = document.getElementById('chatBox');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');

// safe escape
function escapeHtml(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#039;'); }
function appendMessage(role, text){
  const d = document.createElement('div');
  d.className = 'message ' + (role==='user' ? 'user' : (role==='bot' ? 'bot' : 'system'));
  d.innerHTML = escapeHtml(text).replace(/\n/g,'<br>');
  chatBox.appendChild(d);
  chatBox.scrollTop = chatBox.scrollHeight;
}
function clearChat(){ chatBox.innerHTML = ''; }

// load history for current user & god
async function loadHistory(god=currentGod){
  clearChat();
  appendMessage('system', `Loading chat with ${god}...`);
  try{
    const res = await fetch('/history?god=' + encodeURIComponent(god));
    if(!res.ok){ clearChat(); appendMessage('system','Could not load history.'); return; }
    const j = await res.json();
    clearChat();
    const arr = j.history || [];
    if(arr.length===0){ appendMessage('system', `No previous chat with ${god}.`); return; }
    arr.forEach(it => appendMessage(it.role, it.message));
  }catch(e){
    clearChat();
    appendMessage('system','Connection error while loading history.');
    console.error(e);
  }
}

// switch god and load his history
function switchGod(god){
  if(!god) return;
  currentGod = god;
  document.getElementById('chatTitle').textContent = `Chat with ${god}`;
  loadHistory(god);
  // close drawer if used
  document.getElementById('rightDrawer')?.classList.remove('open');
}

// send message
async function sendMessage(){
  const txt = (messageInput.value||'').trim();
  if(!txt) return;
  appendMessage('user', txt);
  messageInput.value = '';
  messageInput.disabled = true;
  sendBtn.disabled = true;
  appendMessage('system', `${currentGod} is thinking...`); // temporary system indicator

  try{
    const res = await fetch('/ask', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({message: txt, god: currentGod})
    });
    const data = await res.json();
    // remove last system indicator
    const systems = Array.from(chatBox.querySelectorAll('.message.system'));
    if(systems.length) systems[systems.length-1].remove();

    if(data.error){ appendMessage('bot', 'Error: ' + data.error); }
    else{ appendMessage('bot', data.reply || data.response || 'No reply'); }
  }catch(err){
    // remove system
    const systems = Array.from(chatBox.querySelectorAll('.message.system'));
    if(systems.length) systems[systems.length-1].remove();
    appendMessage('bot', 'Connection error.');
    console.error(err);
  }finally{
    messageInput.disabled = false;
    sendBtn.disabled = false;
    messageInput.focus();
  }
}

// events
sendBtn?.addEventListener('click', sendMessage);
messageInput?.addEventListener('keypress', function(e){ if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); sendMessage(); } });

// on load, load default god history
window.addEventListener('load', ()=> loadHistory(currentGod));