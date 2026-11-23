// Smash 4 PC's netplay (host/netplay.cpp) is written for Windows only; the port has none.
// These are the four calls the rest of the runtime makes into it.
#include "host/netplay.h"

namespace cafe::host::netplay {
bool remote_pad(int, os::ProPadState&) { return false; }
bool wants_video() { return false; }
void video_frame(const uint8_t*, bool, std::function<void()>, std::function<void()>) {}
void audio(const float*, uint32_t) {}
} // namespace cafe::host::netplay
