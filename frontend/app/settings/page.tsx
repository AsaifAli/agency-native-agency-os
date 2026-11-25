"use client";
import {useState} from "react";
import Page from "@/components/page";
import {clearInMemoryAccessToken,setInMemoryAccessToken} from "@/lib/api";

export default function Settings(){
 const [token,setToken]=useState("");
 const [saved,setSaved]=useState(false);
 if(process.env.NODE_ENV === "production") return <Page eyebrow="SYSTEM CONFIGURATION" title="Settings" description="Authentication is managed by the deployed identity provider."><div className="panel"><div className="notice">Development identity overrides are disabled in production.</div></div></Page>;
 return <Page eyebrow="SYSTEM CONFIGURATION" title="Settings" description="Temporary local development connection settings."><div className="panel"><div className="panel-head"><div className="panel-title">Development identity override</div></div><div className="notice">This token is kept in memory only and is cleared when the page is refreshed or the tab is closed. Never use development tokens in production.</div><label style={{display:"grid",gap:7,fontSize:11,color:"#5f6b80"}}>Development bearer token<input className="field" type="password" placeholder="dev:founder@example.com" value={token} onChange={e=>setToken(e.target.value)}/></label><div style={{display:"flex",gap:9,marginTop:13}}><button className="button" onClick={()=>{setInMemoryAccessToken(token);setSaved(true)}}>Use temporarily</button><button className="button secondary" onClick={()=>{clearInMemoryAccessToken();setToken("");setSaved(false)}}>Clear</button></div>{saved&&<div className="success">Token held in memory for this page session. Refreshing clears it.</div>}</div></Page>
}
