// Used only by the offline build adapter. A fresh browser session starts from demo defaults.
const memory=Object.create(null)
export const sessionStore={getStorageSync:key=>memory[key]===undefined?undefined:JSON.parse(JSON.stringify(memory[key])),setStorageSync:(key,value)=>{memory[key]=JSON.parse(JSON.stringify(value))}}
