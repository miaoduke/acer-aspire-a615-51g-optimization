#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

static long long now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

static void *burn(void *arg) {
    long long *out = (long long *)arg;
    uint32_t x = 123456789;
    long long count = 0;
    long long end = now_ms() + 20000;
    while (now_ms() < end) {
        for (int i = 0; i < 100000; i++) {
            x = (x * 1103515245u + 12345u) & 0x7FFFFFFFu;
            if ((x & 0xFF) == 0) count++;
        }
    }
    *out = count;
    return NULL;
}

int main(int argc, char **argv) {
    pthread_t t[8];
    long long res[8] = {0};
    for (int i = 0; i < 8; i++) pthread_create(&t[i], NULL, burn, &res[i]);
    for (int i = 0; i < 8; i++) pthread_join(t[i], NULL);
    long long total = 0;
    for (int i = 0; i < 8; i++) total += res[i];
    printf("total=%lld\n", total);
    printf("per_thread=");
    for (int i = 0; i < 8; i++) printf("%lld%c", res[i], i == 7 ? '\n' : ',');
    return 0;
}