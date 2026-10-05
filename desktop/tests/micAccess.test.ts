import { describe, expect, it } from "vitest";
import { explainMicError, openMicStream, type MediaDevicesLike } from "../src/voice/micAccess";

const stream = (label: string) => ({ label }) as unknown as MediaStream;
const error = (name: string) => Object.assign(new Error(name), { name });
const device = (id: string, kind = "audioinput") => ({ deviceId: id, kind, label: id }) as MediaDeviceInfo;

function fake(opts: { fail?: Record<string, string>; devices?: MediaDeviceInfo[]; listFails?: boolean }) {
  const calls: string[] = [];
  const media: MediaDevicesLike = {
    async getUserMedia(constraints) {
      const audio = constraints.audio;
      const id = typeof audio === "object" && audio && "deviceId" in audio ? String((audio.deviceId as { exact: string }).exact) : audio === true ? "plain" : "preferred";
      calls.push(id);
      if (opts.fail?.[id]) throw error(opts.fail[id] as string);
      return stream(id);
    },
    async enumerateDevices() {
      if (opts.listFails) throw error("TypeError");
      return opts.devices ?? [];
    },
  };
  return { media, calls };
}

describe("opening the microphone", () => {
  it("uses the preferred settings when they work", async () => {
    const { media, calls } = fake({});

    expect(await openMicStream(media)).toEqual(stream("preferred"));
    expect(calls).toEqual(["preferred"]);
  });

  it("falls back to plain settings", async () => {
    const { media, calls } = fake({ fail: { preferred: "OverconstrainedError" } });

    expect(await openMicStream(media)).toEqual(stream("plain"));
    expect(calls).toEqual(["preferred", "plain"]);
  });

  it("tries each microphone in turn when the default one is not really there", async () => {
    const { media, calls } = fake({
      fail: { preferred: "NotFoundError", plain: "NotFoundError", "dead-1": "NotReadableError" },
      devices: [device("default"), device("communications"), device("dead-1"), device("works-2"), device("camera", "videoinput")],
    });

    expect(await openMicStream(media)).toEqual(stream("works-2"));
    expect(calls).toEqual(["preferred", "plain", "dead-1", "works-2"]);
  });

  it("does not keep asking when Windows says no", async () => {
    const { media, calls } = fake({ fail: { preferred: "NotAllowedError" }, devices: [device("a")] });

    await expect(openMicStream(media)).rejects.toMatchObject({ name: "NotAllowedError" });
    expect(calls).toEqual(["preferred"]);
  });

  it("reports the last error when nothing works, even if listing the devices fails", async () => {
    const { media } = fake({ fail: { preferred: "NotFoundError", plain: "NotFoundError" }, listFails: true });

    await expect(openMicStream(media)).rejects.toMatchObject({ name: "NotFoundError" });
  });
});

describe("saying what went wrong", () => {
  it("tells the learner what to do", () => {
    expect(explainMicError(error("NotAllowedError"))).toContain("Privacy & security");
    expect(explainMicError(error("NotFoundError"))).toContain("No microphone was found");
    expect(explainMicError(error("NotReadableError"))).toContain("Another program");
    expect(explainMicError(error("Weird"))).toContain("Weird");
  });
});
