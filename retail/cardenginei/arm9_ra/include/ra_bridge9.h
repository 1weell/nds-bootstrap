/* GPL-3.0. ARM9 notification producer API; no award/network side effects. */
#ifndef RA_BRIDGE9_H
#define RA_BRIDGE9_H
#include "ra.h"
#include "ra_bridge.h"
extern RaBridgeTx raBridgeSender;
extern RaBridgeStats raBridgeTelemetry;
extern u32 raBridgeTelemetryMagic;
int raBridge9Selected(void);
void raBridge9Tick(raSnapshot *snapshot);
void raBridge9Unlock(u32 id,const char *title);
u8 raBridge9Preview(void);
void raBridge9End(void);
#endif
