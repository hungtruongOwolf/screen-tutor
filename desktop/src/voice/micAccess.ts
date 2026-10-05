// Opening the microphone, and saying what went wrong in words the learner can act on. Takes the
// browser's media devices as a parameter so it is tested with fakes.

export interface MediaDevicesLike {
  getUserMedia(constraints: MediaStreamConstraints): Promise<MediaStream>;
  enumerateDevices(): Promise<MediaDeviceInfo[]>;
}

export function explainMicError(error: unknown): string {
  const name = (error as { name?: string } | null)?.name ?? "Error";
  const raw = (error as { message?: string } | null)?.message ?? String(error);
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "Windows is blocking the microphone. Open Settings, Privacy & security, Microphone, and allow desktop apps to use it.";
  }
  if (name === "NotFoundError" || name === "OverconstrainedError") {
    return "No microphone was found. Plug one in, or switch it on in the Windows Sound settings.";
  }
  if (name === "NotReadableError" || name === "AbortError") {
    return "The microphone could not be started. Another program may be using it.";
  }
  return `The microphone could not be opened (${name}: ${raw}).`;
}

// The preferred settings first, then plain defaults, then every microphone in turn (the default one
// can be a device that is not really there). A refusal by the system is final: asking again
// changes nothing.
export async function openMicStream(devices: MediaDevicesLike): Promise<MediaStream> {
  const attempts: MediaStreamConstraints[] = [
    { audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: false } },
    { audio: true },
  ];
  let last: unknown;
  for (const attempt of attempts) {
    try {
      return await devices.getUserMedia(attempt);
    } catch (error) {
      last = error;
      const name = (error as { name?: string } | null)?.name;
      if (name === "NotAllowedError" || name === "SecurityError") throw error;
    }
  }
  try {
    const microphones = (await devices.enumerateDevices()).filter(
      (d) => d.kind === "audioinput" && d.deviceId && d.deviceId !== "default" && d.deviceId !== "communications",
    );
    for (const microphone of microphones) {
      try {
        return await devices.getUserMedia({ audio: { deviceId: { exact: microphone.deviceId } } });
      } catch (error) {
        last = error;
      }
    }
  } catch {
    // listing the devices failed as well: report the first error
  }
  throw last;
}
