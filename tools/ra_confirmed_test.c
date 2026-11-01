
#include <stdio.h>
#include <string.h>
#include "ra_confirmed.h"
#include "rhash/md5.h"
#define CHECK(x) do { if(!(x)) {fprintf(stderr,"FAIL confirmed %d: %s\n",__LINE__,#x);return 1;} } while(0)
int main(void) {
 raConfirmed a={0},b={0};unsigned char bytes[RA_CONFIRMED_BYTES],bad[RA_CONFIRMED_BYTES];
 char key[33],other[33];
 raConfirmedUserKey("Player",key);raConfirmedUserKey("pLaYeR",other);CHECK(!strcmp(key,other));
 CHECK(!strcmp(key,"912af0dff974604f1321254ca8ff38b6"));
 CHECK(raConfirmedAdd(&a,230045)==1);CHECK(raConfirmedAdd(&a,230047)==1);
 CHECK(raConfirmedAdd(&a,230045)==0 && a.count==2);
 CHECK(raConfirmedAdd(&a,0)<0 && raConfirmedAdd(&a,101000001)<0);
 int size=raConfirmedEncode(&a,"Player",bytes,sizeof(bytes));CHECK(size==48);
 static const unsigned char expected[]={82,65,67,49,145,42,240,223,249,116,96,79,19,33,37,76,168,255,56,182,2,0,0,0,157,130,3,0,159,130,3,0,15,248,38,188,53,233,62,171,27,244,151,74,142,247,36,176};
 CHECK(sizeof(expected)==(unsigned)size && !memcmp(bytes,expected,size));
 CHECK(raConfirmedDecode(&b,"PLAYER",bytes,size) && b.count==2);
 CHECK(!raConfirmedDecode(&b,"OtherAccount",bytes,size) && b.count==2);
 for(int n=0;n<size;++n) CHECK(!raConfirmedDecode(&b,"Player",bytes,n) && b.count==2);
 for(int n=0;n<size;++n) {memcpy(bad,bytes,size);bad[n]^=1;CHECK(!raConfirmedDecode(&b,"Player",bad,size) && b.count==2);}
 uint32_t stale[5]={230041,230044,0,0,0xDEADBEEF};
 CHECK(raConfirmedMerge(&a,stale,2,4)==4);
 CHECK(stale[0]==230041 && stale[1]==230044 && stale[2]==230045 && stale[3]==230047 && stale[4]==0xDEADBEEF);
 CHECK(raConfirmedMerge(&a,stale,4,4)==4);
 memset(&a,0,sizeof(a));for(unsigned i=1;i<=RA_CONFIRMED_MAX;++i)CHECK(raConfirmedAdd(&a,i)==1);
 CHECK(raConfirmedAdd(&a,999)<0);
 size=raConfirmedEncode(&a,"Player",bytes,sizeof(bytes));CHECK(size==RA_CONFIRMED_BYTES);
 CHECK(raConfirmedEncode(&a,"Player",bad,size-1)<0);
 CHECK(raConfirmedDecode(&b,"Player",bytes,size) && b.count==RA_CONFIRMED_MAX);
 puts("PASSED confirmed ledger: independent fixture, account binding, corruption, truncation, capacity, stale lookup merge");
 return 0;
}
