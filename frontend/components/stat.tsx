export default function Stat({label,value,foot,icon}:{label:string;value:string|number;foot:string;icon:string}){
 return <div className="stat"><div className="stat-top"><span>{label}</span><span className="stat-icon">{icon}</span></div><div className="stat-value">{value}</div><div className="stat-foot">{foot}</div></div>
}
