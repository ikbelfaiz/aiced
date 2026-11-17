// Observe real responses without changing assertions, retry policy or application traffic.
import { test } from '@playwright/test';
import { appendFileSync } from 'node:fs';
import { join } from 'node:path';
export function pipelineDiagnostics(){
  test.beforeEach(async({page},info)=>{
    const directory=process.env.AICED_E2E_REPORT_DIR;
    if(!directory)return;
    const write=(value:object)=>appendFileSync(join(directory,'pipeline-requests.jsonl'),JSON.stringify({test:info.title,time:new Date().toISOString(),...value})+'\n');
    page.on('request',request=>{
      if(new URL(request.url()).pathname==='/api/opportunities/')write({event:'request',url:request.url()});
    });
    page.on('requestfailed',request=>{
      if(new URL(request.url()).pathname==='/api/opportunities/')write({event:'failed',url:request.url(),failure:request.failure()});
    });
    page.on('response',async response=>{
      if(new URL(response.url()).pathname!=='/api/opportunities/')return;
      const headers=await response.allHeaders();
      const value={event:'response',url:response.url(),status:response.status(),request_id:headers['x-request-id']};
      try{
        const body=await response.json();
        write({...value,timing:response.request().timing(),body:response.ok()?{count:body.count,statuses:body.statuses}:body});
      }catch{write({...value,body_unavailable:true});}
    });
  });
}
