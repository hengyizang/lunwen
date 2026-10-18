// One-process credential handoff. The RSA private key never leaves memory.
const crypto = require('node:crypto');
const readline = require('node:readline');
const {publicKey, privateKey} = crypto.generateKeyPairSync('rsa', {modulusLength: 3072});
process.stdout.write(JSON.stringify({public_key_pem: publicKey.export({type:'spki', format:'pem'})})+'\n');
const lines = readline.createInterface({input: process.stdin});
lines.once('line', line => {
  try {
    const e = JSON.parse(line);
    if (e.version !== 1) throw Error('version');
    const key = crypto.privateDecrypt({key:privateKey, padding:crypto.constants.RSA_PKCS1_OAEP_PADDING,
      oaepHash:'sha256'}, Buffer.from(e.wrapped_key, 'base64'));
    const decipher = crypto.createDecipheriv('aes-256-gcm', key, Buffer.from(e.iv,'base64'));
    decipher.setAAD(Buffer.from(e.aad,'utf8'));
    decipher.setAuthTag(Buffer.from(e.tag,'base64'));
    const plain = Buffer.concat([decipher.update(Buffer.from(e.ciphertext,'base64')), decipher.final()]);
    process.stdout.write(plain.toString('utf8')+'\n');
    key.fill(0); plain.fill(0);
  } catch (_) { process.stderr.write('Credential envelope rejected\n'); process.exitCode=1; }
  lines.close();
});
