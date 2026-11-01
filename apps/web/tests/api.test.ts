import {afterEach,describe,it,expect,vi} from 'vitest';
import {request,dateTime,money} from '../lib/api';
afterEach(()=>vi.unstubAllGlobals());
describe('Session-bound API client',()=>{
 it('sends CSRF for mutations and keeps the same-origin session',async()=>{
  const fetcher=vi.fn().mockResolvedValue({ok:true,status:200,json:async()=>({created:773})});vi.stubGlobal('fetch',fetcher);
  const result=await request('/v1/workspaces/a/imports/id/commit',{method:'POST',body:'{}'},'csrf-example');
  expect(result).toEqual({created:773});const [url,init]=fetcher.mock.calls[0];expect(url).toBe('/api/v1/workspaces/a/imports/id/commit');expect(init.credentials).toBe('same-origin');expect(init.headers.get('X-CSRF-Token')).toBe('csrf-example');expect(init.headers.get('Content-Type')).toBe('application/json');
 });
 it('preserves the browser multipart boundary for CSV uploads',async()=>{const fetcher=vi.fn().mockResolvedValue({ok:true,status:200,json:async()=>({})});vi.stubGlobal('fetch',fetcher);const body=new FormData();body.append('file',new File(['First Name,Last Name\nDemo,Person'],'demo.csv'));await request('/v1/workspaces/a/imports/preview',{method:'POST',body},'csrf');expect(fetcher.mock.calls[0][1].headers.has('Content-Type')).toBe(false)});
 it('surfaces authorization failure instead of treating it as empty data',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,status:403,json:async()=>({message:'Kein Zugriff auf diesen Workspace.'})}));await expect(request('/v1/workspaces/b/contacts')).rejects.toMatchObject({status:403,message:'Kein Zugriff auf diesen Workspace.'});});
});
describe('German display conventions',()=>{
 it('renders integer minor units as euros',()=>expect(money(123400)).toContain('1.234'));
 it('uses Berlin daylight saving time consistently for UTC appointments',()=>{expect(dateTime('2026-10-25T00:30:00Z')).toContain('02:30');expect(dateTime('2026-10-25T01:30:00Z')).toContain('02:30')});
});
