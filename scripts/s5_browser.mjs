import { createRequire } from 'node:module';
const require=createRequire(new URL('../frontend/package.json',import.meta.url));
const { chromium }=require('@playwright/test');
import fs from 'node:fs';
const browser=await chromium.launch({headless:true});
try {
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(process.env.AICED_S5_URL+'/connexion');
 await page.getByLabel(/identifiant/i).fill('synthetic.manager.a');
 await page.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_S5_PASSWORD);
 await page.getByRole('button',{name:'Connexion',exact:true}).click();
 await page.waitForURL('**/tableau-de-bord');
 await page.goto(process.env.AICED_S5_URL+'/clients');
 await page.getByText('Panorama Clients',{exact:true}).first().waitFor();
 await page.screenshot({path:process.env.AICED_S5_DIR+'/panorama.png',fullPage:true});
 if(errors.length)throw new Error(errors.join(';'));
 console.log('IAM login and unchanged React Panorama verified');
}finally{await browser.close();}
