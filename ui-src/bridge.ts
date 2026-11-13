// Connection to the Python core over Qt WebChannel (design document 3.1).
// The interface has no file access of its own; everything goes through here.

declare const QWebChannel: any;
declare const qt: any;

let core: any = null;

export function connect(): Promise<void> {
  return new Promise((resolve) => {
    new QWebChannel(qt.webChannelTransport, (channel: any) => {
      core = channel.objects.core;
      resolve();
    });
  });
}

export function call<T = any>(name: string, ...args: unknown[]): Promise<T> {
  return new Promise((resolve, reject) => {
    core[name](...args, (reply: string) => {
      try {
        resolve(reply ? JSON.parse(reply) : (null as T));
      } catch (error) {
        reject(error);
      }
    });
  });
}

export function on(signal: string, handler: (data: any) => void): void {
  core[signal].connect((reply: string) => handler(reply ? JSON.parse(reply) : null));
}
