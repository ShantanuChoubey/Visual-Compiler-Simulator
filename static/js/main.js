const frog=document.getElementById("frog");
const game=document.getElementById("gameArea");
const status=document.getElementById("status");
const codeInput=document.getElementById("codeInput");
const tokens=document.getElementById("tokens");
const parseTree=document.getElementById("parseTree");

let x=200,y=300;

function clamp(){
x=Math.max(0,Math.min(x,game.clientWidth-50));
y=Math.max(0,Math.min(y,game.clientHeight-50));
}

function update(){
clamp();
frog.style.left=x+"px";
frog.style.top=y+"px";
}

function runCode(){

status.innerText="Running...";
tokens.innerText="";
parseTree.innerText="";

let cmds=codeInput.value.split("\n").filter(l=>l.trim());
let delay=0;

cmds.forEach((c,i)=>{
tokens.innerText+=c.replace(/[();]/g,"")+" | ";
parseTree.innerText+=`Command ${i+1}: ${c}\n`;
setTimeout(()=>exec(c),delay);
delay+=600;
});

setTimeout(()=>status.innerText="Ready",delay);
}

function exec(c){

if(c.startsWith("moveRight"))x+=40;
if(c.startsWith("moveLeft"))x-=40;

if(c.startsWith("jump")){
y-=60;
setTimeout(()=>{y+=60;update()},300);
}

if(c.startsWith("glow"))frog.style.filter="drop-shadow(0 0 15px lime)";
if(c.startsWith("spin"))frog.style.transform="rotate(360deg)";
if(c.startsWith("dash"))x+=80;
if(c.startsWith("float"))frog.style.transform="translateY(-20px)";

setTimeout(()=>{
frog.style.filter="";
frog.style.transform="";
},400);

update();
}

function addCommand(c){codeInput.value+=c+"\n";}
function undoLastCommand(){
let l=codeInput.value.trim().split("\n");
l.pop();codeInput.value=l.join("\n")+"\n";
}
function clearCode(){codeInput.value="";}

update();
