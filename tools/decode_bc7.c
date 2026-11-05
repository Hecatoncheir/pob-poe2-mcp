/* Переносимое декодирование исходных текстур PoB; без игровых правил. */
#define BCDEC_IMPLEMENTATION
#include "bcdec.h"
#include <string.h>

void pob_decode_bc7(const unsigned char *source, int width, int height, unsigned char *target) {
    unsigned char block[64];
    int x, y, row;
    for (y = 0; y < height; y += 4) {
        for (x = 0; x < width; x += 4) {
            bcdec_bc7(source, block, 16);
            source += 16;
            for (row = 0; row < 4 && y + row < height; row++) {
                int count = width - x < 4 ? width - x : 4;
                memcpy(target + ((y + row) * width + x) * 4, block + row * 16, count * 4);
            }
        }
    }
}
