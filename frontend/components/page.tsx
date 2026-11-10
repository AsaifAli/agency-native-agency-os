import type { ReactNode } from "react";
export default function Page({eyebrow,title,description,action,children}:{eyebrow:string;title:string;description:string;action?:ReactNode;children:ReactNode}){
 return <div className="content"><div className="page-head"><div><div className="eyebrow">{eyebrow}</div><h1 className="page-title">{title}</h1><p className="page-desc">{description}</p></div>{action}</div>{children}</div>
}
