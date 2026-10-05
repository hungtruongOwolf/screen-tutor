// `npm run setup:voice [-- --voice en_US-ryan-high] [--listen-only]`: the same download the app does
// by itself the first time it starts.
import { installVoice } from "./installer";

const args = process.argv.slice(2);
const at = args.indexOf("--voice");
let last = "";
installVoice({
  voice: at >= 0 ? args[at + 1] : undefined,
  listenOnly: args.includes("--listen-only"),
  progress: (what, fraction) => {
    const line = fraction === undefined ? what : `${what} ${Math.round(fraction * 100)} %`;
    if (line !== last) console.log(line);
    last = line;
  },
}).then(
  () => console.log("done"),
  (error: Error) => {
    console.error(error.message);
    process.exit(1);
  },
);
