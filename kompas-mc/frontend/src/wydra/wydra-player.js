export const STATES={
  "nasluchiwanie": {"label":"Nasłuchiwanie","pose":"stoi","ms":5800},
  "skupienie": {"label":"Skupienie","pose":"sklada","ms":6600},
  "radosc": {"label":"Radość","pose":"stoi","ms":5200},
  "sennosc": {"label":"Senność","pose":"sklada","ms":7800},
  "machanie": {"label":"Machanie","pose":"stoi","ms":3600},
  "podskok": {"label":"Podskok","pose":"stoi","ms":3000},
  "proszenie": {"label":"Proszenie","pose":"prosi","ms":4400}
};
const v = `
attribute vec2 a;
varying vec2 uv;
uniform float pose, wave, tail, nod, lean, dip, lift, tuck, offer, stretch;
uniform vec4 expr, details;
uniform vec2 headShift;
float bell(vec2 p, vec2 center, vec2 radius){
  vec2 q=(p-center)/radius;
  return exp(-dot(q,q)*1.7);
}
float ramp(float lo,float hi,float val){return smoothstep(lo,hi,val);}
vec2 turn(vec2 p,vec2 center,float deg){
  float a=radians(deg);vec2 q=p-center;
  return center+vec2(q.x*cos(a)-q.y*sin(a),q.x*sin(a)+q.y*cos(a));
}
void main(){
  uv=a;vec2 p=a*vec2(578.,649.);float x=p.x,y=p.y;
  bool front=pose<0.5;
  vec2 browL=front?vec2(161.,137.):vec2(161.,149.);
  vec2 browR=front?vec2(318.,106.):vec2(293.,84.);
  p.y-=expr.x*bell(p,browL,vec2(34.,18.));
  p.y-=expr.y*bell(p,browR,vec2(34.,17.));
  vec2 cornerL=front?vec2(203.,245.):vec2(213.,246.);
  vec2 cornerR=front?vec2(326.,224.):vec2(339.,195.);
  p+=vec2(-3.5,-6.0)*expr.z*bell(p,cornerL,vec2(39.,33.));
  p+=vec2(3.1,-5.4)*expr.z*bell(p,cornerR,vec2(42.,32.));
  vec2 mouth=front?vec2(269.,248.):vec2(279.,241.);
  vec2 axis=front?vec2(.16,.985):vec2(.42,.908);
  float along=dot(p-mouth,axis);
  p+=axis*expr.w*5.6*ramp(-3.,5.,along)*bell(p,mouth+axis*7.,vec2(34.,23.));
  vec2 nose=front?vec2(261.,204.):vec2(267.,200.);
  p.y-=details.z*2.8*bell(p,nose,vec2(36.,24.));
  vec2 earL=front?vec2(94.,167.):vec2(91.,183.);
  vec2 earR=front?vec2(387.,93.):vec2(366.,48.);
  p+=vec2(-3.8,-5.4)*details.x*bell(p,earL,vec2(35.,39.));
  p+=vec2(3.3,-5.7)*details.y*bell(p,earR,vec2(35.,36.));
  if(pose>1.5){
    p+=vec2(4.,-8.)*details.w*bell(p,vec2(294.,431.),vec2(57.,62.));
    p+=vec2(-3.,-4.)*details.w*bell(p,vec2(357.,420.),vec2(37.,49.));
  }
  // Each weight follows the silhouette of a joint and softens into its attachment.
  if(pose<0.5){
    float paw=ramp(380.,436.,x+.35*(y-270.))*(1.-ramp(317.,388.,y));
    p=turn(p,vec2(390.,354.),wave*paw);
    float tailMask=ramp(405.,482.,x)*(ramp(320.,366.,y))*(1.-ramp(525.,588.,y));
    p=turn(p,vec2(431.,540.),tail*tailMask);
    float freeArm=(1.-ramp(85.,175.,x))*ramp(309.,392.,y)*(1.-ramp(471.,515.,y));
    p=turn(p,vec2(152.,356.),tuck*33.*freeArm);
    float toes=ramp(515.,620.,y);
    float side=ramp(250.,313.,x)*2.-1.;
    p.x+=side*tuck*15.*toes; p.y-=tuck*(23.+side*5.)*toes;
  }else{
    float palm=(1.-ramp(98.,233.,x))*ramp(306.,350.,y)*(1.-ramp(445.,500.,y));
    p=turn(p,vec2(208.,358.),offer*14.*palm);
    p.x-=offer*9.*palm;
    float tailMask=(1.-ramp(75.,190.,x))*ramp(465.,506.,y);
    p=turn(p,vec2(172.,563.),tail*tailMask);
  }
  float head=(1.-ramp(254.,371.,y))*(1.-ramp(392.,445.,x)*ramp(173.,278.,y));
  p=turn(p,vec2(252.,315.),nod*head)+headShift*head;
  p=turn(p,vec2(283.,635.),lean*(1.-ramp(510.,630.,y)));
  float h=(639.-p.y)/639.;
  p.y+=h*(dip-stretch);
  p.x+=(p.x-282.)*h*(dip-stretch)*.00058;
  p+=vec2(36.,121.-lift);
  gl_Position=vec4(2.*p.x/650.-1.,1.-2.*p.y/786.,0.,1.);
}`;

const f = `precision highp float;
varying vec2 uv;
uniform sampler2D art, lidArt;
uniform float pose;
uniform vec4 eyes,expr;
const vec2 size=vec2(578.,649.);
vec4 sampleArt(vec2 p){return texture2D(art,p/size);}
vec3 lidAt(vec2 p){
  vec2 q=p-vec2(134.,92.);
  q.y=clamp(q.y,.5,154.5)+(pose<.5?0.:155.);
  return texture2D(lidArt,q/vec2(240.,310.)).rgb;
}
vec4 eyelid(vec2 p,vec2 center,vec2 radii,float slope,vec3 crease,float close,vec4 original){
  vec2 local=p-center;
  float u=local.x/radii.x;
  float q=(local.y-slope*local.x)/radii.y;
  float radial=length(vec2(u,q));
  if(radial>1.76) return original;
  float gazeWeight=1.-smoothstep(.50,.99,radial);
  vec4 eye=sampleArt(p-eyes.zw*gazeWeight);
  if(close<.0005) return eye;
  float arc=sqrt(max(0.,1.-u*u));
  float middle=center.y+slope*local.x;
  float top=middle-radii.y*arc,bottom=middle+radii.y*arc;
  float seam=center.y+crease.x+local.x*(crease.y+crease.z*local.x);
  float cheeks=clamp(expr.z,0.,1.)*close*(1.-close);
  float upper=mix(top,seam,close-.48*cheeks),lower=mix(bottom,seam,close+.70*cheeks);
  float upperCoverage=1.-smoothstep(-.55,.55,p.y-upper);
  float lowerCoverage=smoothstep(-.55,.55,p.y-lower);
  float area=(1.-smoothstep(1.10,1.53,radial))*smoothstep(.0,.20,close);
  area*=1.-smoothstep(.90,1.22,abs(u));
  float upFollow=1.-smoothstep(0.,30.,abs(p.y-upper));
  float lowFollow=1.-smoothstep(0.,24.,abs(p.y-lower));
  vec3 topLid=lidAt(p+vec2(0.,(seam-upper-1.1)*upFollow));
  vec3 bottomLid=lidAt(p+vec2(0.,(seam-lower+4.6)*lowFollow));
  vec3 color=mix(eye.rgb,topLid,area*upperCoverage);
  color=mix(color,bottomLid,area*lowerCoverage);
  // Converge to the registered closed eyelid at contact, including the two corners.
  color=mix(color,lidAt(p),smoothstep(.77,1.,close)*(1.-smoothstep(1.42,1.75,radial)));
  return vec4(color,eye.a);
}
void main(){
  vec2 p=uv*size;vec4 base=texture2D(art,uv);
  bool front=pose<.5;
  vec4 c=eyelid(p,front?vec2(186.,191.):vec2(190.,201.),front?vec2(25.5,24.):vec2(25.5,26.5),
    front?-.24:-.38,front?vec3(11.85,-.174,.001):vec3(12.11,-.355,-.004),eyes.x,base);
  c=eyelid(p,front?vec2(325.,162.):vec2(318.,134.),front?vec2(26.6,24.):vec2(26.5,25.),
    front?.12:-.14,front?vec3(9.88,-.363,.007):vec3(14.89,-.497,-.009),eyes.y,c);
  gl_FragColor=c;
}`;

function smooth(x) {
  x=Math.max(0,Math.min(1,x));
  return x*x*(3-2*x);
}
function rise(t,a,b){return smooth((t-a)/(b-a));}
function hold(t,a,b,c,d){return rise(t,a,b)*(1-rise(t,c,d));}
function blink(t,start,down=.077,shut=.026,up=.132){
  return hold(t,start,start+down,start+down+shut,start+down+shut+up);
}
function performanceAt(move,t,duration){
  const H=(a,b,c,d)=>hold(t,a,b,c,d);
  const B=(start,down,shut,up)=>blink(t,start,down,shut,up);
  const sin=(phase)=>Math.sin(2*Math.PI*phase);
  const breathe=Math.sin(Math.PI*t/duration)**2*(.46+.54*Math.cos(2*Math.PI*(t-.28)/3.35));
  let wave=0,tail=0,nod=0,lean=0,dip=0,lift=0,tuck=0,offer=0,stretch=2*breathe;
  let wink=0,shut=0,squint=0,gazeX=0,gazeY=0,browL=0,browR=0,smile=0,jaw=0,earL=0,earR=0,nose=0,paws=0,headX=0,headY=0;
  if(move==='nasluchiwanie'){
    // Two separate sounds. Eyes arrive first, then the near ear, then the head.
    const left=H(.30,.41,1.72,2.22),right=H(2.36,2.47,4.55,5.25);
    gazeX=-4.7*left+4.4*right; gazeY=-1.4*left-2.1*right;
    nod=-4.7*H(.54,1.12,1.85,2.38)+5.3*H(2.61,3.24,4.45,5.47);
    headX=-3.0*left+3.2*right;
    browL=5.8*left+1.1*right;browR=1.2*left+6.0*right;
    earL=1.65*H(.38,.53,.62,.94)+.6*H(1.26,1.39,1.42,1.63);
    earR=1.45*H(2.44,2.6,2.72,3.03)+.68*H(3.75,3.89,3.94,4.16);
    wave=-3.2*H(.49,1.12,3.9,5.14);tail=3.5*H(.76,1.46,1.85,2.46)-2.6*H(2.92,3.77,4.38,5.47);
    shut=B(2.04)+B(4.91);nose=.65*B(1.48,.1,.04,.16)+.65*B(3.98,.09,.025,.16);
  }else if(move==='skupienie'){
    const study=H(.4,1.1,4.72,5.61),reading=H(1.08,1.19,2.27,2.45),
          second=H(2.52,2.68,3.35,3.53),idea=H(4.58,4.93,5.64,6.34);
    gazeX=-3.9*reading+3.5*second-2.1*H(3.56,3.68,4.23,4.42)+2.4*idea;
    gazeY=3.8*study-3.*idea;headY=5.8*study-2.7*idea;
    nod=-3.6*study+2.3*idea;browL=-4.7*study+5.4*idea;browR=-2.0*study+3.6*idea;
    squint=.18*study;shut=B(.26)+B(4.29,.088,.033,.16)+B(5.95);
    paws=.82*H(.7,1.47,1.79,2.27)+.6*H(2.78,3.23,3.55,4.13);
    smile=.7*idea;tail=2.8*H(1.44,2.61,3.75,5.11);earR=.72*idea;
  }else if(move==='radosc'){
    const recognition=H(.18,.57,.96,1.35),happy=H(.54,1.32,3.9,4.9);
    browL=6.4*recognition+2*happy;browR=5.8*recognition+3*happy;
    gazeY=-2.3*recognition;smile=1.25*happy;jaw=.98*happy;
    squint=.34*happy;shut=B(.14)+B(1.66,.095,.058,.17)+B(3.78);
    lean=-2.1*happy;nod=-2.5*happy+1.35*happy*sin((t-1.12)/1.24);
    dip=happy*(2.9+3.1*sin((t-.76)/.85));wave=happy*(3.5+6.2*sin((t-.67)/.87));
    tail=happy*7.4*sin((t-.8)/1.20);earR=.82*recognition;
    nose=.65*H(2.47,2.58,2.72,2.9);
  }else if(move==='sennosc'){
    const tired=H(.38,2.2,6.27,7.47),droop=H(2.98,4.06,5.82,6.72);
    squint=.28*tired;shut=Math.max(B(1.0,.22,.11,.36),B(2.48,.28,.10,.3),B(3.71,.6,1.48,.62),B(6.48,.10,.055,.21));
    nod=3.1*tired+3.1*droop;headY=2.9*tired+5.3*droop;
    browL=-1.8*tired;browR=-2.3*tired;gazeY=2.5*tired;
    jaw=.7*H(2.7,3.52,3.88,4.56);smile=.45*droop;
    paws=-.45*droop;stretch+=2.8*tired*sin((t-.55)/2.8);
    tail=2.4*H(1.2,2.94,4.6,6.9);earL=-.65*tired;earR=-.82*tired;
  }else if(move==='machanie'){
    const greeting=H(.22,.74,2.73,3.49),beats=H(.56,.89,2.37,2.93);
    gazeX=2.7*H(.10,.23,.39,.72);browR=5.4*greeting;browL=2.7*greeting;
    smile=.94*greeting;squint=.14*greeting;shut=B(.37)+B(2.78);
    wave=-3.7*greeting+beats*(1.7+13.9*sin((t-.72)/.77));
    nod=-3.5*greeting;lean=-1.5*greeting;tail=4.7*greeting*sin((t-.82)/1.38);
    earR=.72*H(.39,.53,.69,.97);
  }else if(move==='podskok'){
    function hop(start,height,length,scale){
      const u=(t-start)/length,air=Math.max(0,Math.min(1,(u-.23)/.48));
      lift+=height*4*air*(1-air);
      const curl=hold(u,.22,.42,.54,.74);
      tuck+=scale*curl;stretch+=scale*8*hold(u,.13,.22,.24,.35);
      dip+=scale*(25*hold(u,0,.13,.14,.23)+19*hold(u,.70,.78,.79,.93));
      wave-=8*curl*scale;tail+=8*hold(u,.21,.44,.57,.83)*scale;
      browL+=5.2*curl;browR+=4.5*curl;smile+=.62*curl;jaw+=.64*curl;
    }
    hop(.27,98,1.05,1);hop(1.53,50,.87,.68);
    gazeY=-2.8*H(.07,.19,.74,1.1)-1.8*H(1.39,1.47,1.89,2.2);
    shut=B(1.09,.06,.021,.12)+B(2.19,.063,.022,.13);nod=-1.6*tuck;
    smile+=.4*H(2.25,2.42,2.6,2.97);
  }else if(move==='proszenie'){
    const invite=H(.46,1.49,2.96,4.17),glance=H(.17,.34,1.23,1.57);
    gazeX=-4.1*glance;gazeY=2.6*glance;shut=B(.10)+B(1.55)+B(3.53);
    browL=4.1*invite;browR=6.4*invite;smile=.67*invite;
    nod=-4.3*invite;lean=-1.8*invite;offer=invite+.22*H(2.19,2.48,2.64,3.01);
    headY=2.5*H(2.08,2.47,2.68,3.05);tail=3.4*H(.84,1.73,2.92,4.22);
    dip=3*invite;earL=.52*invite;
  }
  const left=Math.min(1,shut+squint*(1-shut));
  const right=Math.min(1,shut+(squint*.93+wink)*(1-shut));
  return {
    body:[wave,tail,nod,lean,dip,lift,tuck,offer,stretch],
    eyes:[left,right,gazeX,gazeY],expr:[browL,browR,smile,jaw],
    details:[earL,earR,nose,paws],head:[headX,headY]
  };
}

export async function makePlayer(canvas,url,pose,lidsURL){
  const image=new Image();
  image.src=url;
  const lids=new Image();lids.src=lidsURL;
  await Promise.all([image.decode(),lids.decode()]);
  const gl=canvas.getContext("webgl",{alpha:true,premultipliedAlpha:true,preserveDrawingBuffer:true,antialias:false});
  if(!gl)throw Error("WebGL unavailable");
  const shaders=[],buffers=[];
  const program=gl.createProgram(),texture=gl.createTexture(),lidTexture=gl.createTexture();
  function dispose(){
    for(const b of buffers)gl.deleteBuffer(b);
    gl.deleteTexture(lidTexture);gl.deleteTexture(texture);gl.deleteProgram(program);
    for(const s of shaders)gl.deleteShader(s);
    gl.getExtension('WEBGL_lose_context')?.loseContext();
  }
  function attach(kind,source){
    const s=gl.createShader(kind);shaders.push(s);gl.shaderSource(s,source);gl.compileShader(s);
    if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));
    gl.attachShader(program,s);
  }
  function buffer(type,data){
    const b=gl.createBuffer();buffers.push(b);gl.bindBuffer(type,b);gl.bufferData(type,data,gl.STATIC_DRAW);
  }
  try{
    attach(gl.VERTEX_SHADER,v);attach(gl.FRAGMENT_SHADER,f);gl.linkProgram(program);
    if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));
    gl.useProgram(program);
    const vert=[],idx=[],nx=96,ny=108;
    for(let y=0;y<=ny;y++)for(let x=0;x<=nx;x++)vert.push(x/nx,y/ny);
    for(let y=0;y<ny;y++)for(let x=0;x<nx;x++){const i=y*(nx+1)+x;idx.push(i,i+1,i+nx+1,i+1,i+nx+2,i+nx+1);}
    buffer(gl.ARRAY_BUFFER,new Float32Array(vert));buffer(gl.ELEMENT_ARRAY_BUFFER,new Uint16Array(idx));
    const pos=gl.getAttribLocation(program,'a');gl.enableVertexAttribArray(pos);gl.vertexAttribPointer(pos,2,gl.FLOAT,false,0,0);
    for(const [index,tex,bitmap] of [[0,texture,image],[1,lidTexture,lids]]){
      gl.activeTexture(gl.TEXTURE0+index);gl.bindTexture(gl.TEXTURE_2D,tex);
      gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL,true);
      for(const [name,value] of [[gl.TEXTURE_MIN_FILTER,gl.LINEAR],[gl.TEXTURE_MAG_FILTER,gl.LINEAR],[gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE],[gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE]])gl.texParameteri(gl.TEXTURE_2D,name,value);
      gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,bitmap);
    }
    const loc=k=>gl.getUniformLocation(program,k);
    gl.uniform1i(loc('lidArt'),1);
    const body='wave tail nod lean dip lift tuck offer stretch'.split(' ').map(loc);
    const eyes=loc('eyes'),expr=loc('expr'),details=loc('details'),head=loc('headShift');
    gl.uniform1f(loc('pose'),{stoi:0,prosi:1,sklada:2}[pose]);
    return {dispose,draw(move,time){
      const p=performanceAt(move,time/1000,STATES[move].ms/1000);
      body.forEach((l,i)=>gl.uniform1f(l,p.body[i]));
      gl.uniform4fv(eyes,p.eyes);gl.uniform4fv(expr,p.expr);gl.uniform4fv(details,p.details);gl.uniform2fv(head,p.head);
      gl.clear(gl.COLOR_BUFFER_BIT);gl.drawElements(gl.TRIANGLES,idx.length,gl.UNSIGNED_SHORT,0);
    }};
  }catch(e){dispose();throw e;}
}
