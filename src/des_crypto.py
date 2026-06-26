# -*- coding: utf-8 -*-
"""
des_crypto.py — DES 加密算法的纯 Python 实现
从 des.js 完整转写而来，保持算法逻辑完全一致
"""

# === 辅助函数 ===

def get_box_binary(i):
    """将 0-15 的整数转换为 4 位二进制字符串"""
    binary = ""
    if i == 0:   binary = "0000"
    elif i == 1: binary = "0001"
    elif i == 2: binary = "0010"
    elif i == 3: binary = "0011"
    elif i == 4: binary = "0100"
    elif i == 5: binary = "0101"
    elif i == 6: binary = "0110"
    elif i == 7: binary = "0111"
    elif i == 8: binary = "1000"
    elif i == 9: binary = "1001"
    elif i == 10: binary = "1010"
    elif i == 11: binary = "1011"
    elif i == 12: binary = "1100"
    elif i == 13: binary = "1101"
    elif i == 14: binary = "1110"
    elif i == 15: binary = "1111"
    return binary


def bt4_to_hex(binary):
    """4 位比特字符串转十六进制字符"""
    hex_val = ""
    if binary == "0000":   hex_val = "0"
    elif binary == "0001": hex_val = "1"
    elif binary == "0010": hex_val = "2"
    elif binary == "0011": hex_val = "3"
    elif binary == "0100": hex_val = "4"
    elif binary == "0101": hex_val = "5"
    elif binary == "0110": hex_val = "6"
    elif binary == "0111": hex_val = "7"
    elif binary == "1000": hex_val = "8"
    elif binary == "1001": hex_val = "9"
    elif binary == "1010": hex_val = "A"
    elif binary == "1011": hex_val = "B"
    elif binary == "1100": hex_val = "C"
    elif binary == "1101": hex_val = "D"
    elif binary == "1110": hex_val = "E"
    elif binary == "1111": hex_val = "F"
    return hex_val


def hex_to_bt4(hex_val):
    """十六进制字符转 4 位比特字符串"""
    binary = ""
    if hex_val == "0":   binary = "0000"
    elif hex_val == "1": binary = "0001"
    elif hex_val == "2": binary = "0010"
    elif hex_val == "3": binary = "0011"
    elif hex_val == "4": binary = "0100"
    elif hex_val == "5": binary = "0101"
    elif hex_val == "6": binary = "0110"
    elif hex_val == "7": binary = "0111"
    elif hex_val == "8": binary = "1000"
    elif hex_val == "9": binary = "1001"
    elif hex_val == "A": binary = "1010"
    elif hex_val == "B": binary = "1011"
    elif hex_val == "C": binary = "1100"
    elif hex_val == "D": binary = "1101"
    elif hex_val == "E": binary = "1110"
    elif hex_val == "F": binary = "1111"
    return binary


def str_to_bt(s):
    """将长度 <= 4 的字符串转换为 64 位比特数组"""
    leng = len(s)
    bt = [0] * 64
    if leng < 4:
        for i in range(leng):
            k = ord(s[i])
            for j in range(16):
                pow_val = 1
                for m in range(15, j, -1):
                    pow_val *= 2
                bt[16 * i + j] = int(k / pow_val) % 2
        for p in range(leng, 4):
            k = 0
            for q in range(16):
                pow_val = 1
                for m in range(15, q, -1):
                    pow_val *= 2
                bt[16 * p + q] = int(k / pow_val) % 2
    else:
        for i in range(4):
            k = ord(s[i])
            for j in range(16):
                pow_val = 1
                for m in range(15, j, -1):
                    pow_val *= 2
                bt[16 * i + j] = int(k / pow_val) % 2
    return bt


def get_key_bytes(key):
    """将密钥字符串转换为比特数组列表（每组 64 位）"""
    key_bytes = []
    leng = len(key)
    iterator = int(leng / 4)
    remainder = leng % 4
    for i in range(iterator):
        key_bytes.append(str_to_bt(key[i * 4:i * 4 + 4]))
    if remainder > 0:
        key_bytes.append(str_to_bt(key[iterator * 4:leng]))
    return key_bytes


def byte_to_string(byte_data):
    """将 64 位比特数组转换回字符串"""
    s = ""
    for i in range(4):
        count = 0
        for j in range(16):
            pow_val = 1
            for m in range(15, j, -1):
                pow_val *= 2
            count += byte_data[16 * i + j] * pow_val
        if count != 0:
            s += chr(count)
    return s


def bt64_to_hex(byte_data):
    """将 64 位比特数组转换为 16 位十六进制字符串"""
    hex_str = ""
    for i in range(16):
        bt = ""
        for j in range(4):
            bt += str(byte_data[i * 4 + j])
        hex_str += bt4_to_hex(bt)
    return hex_str


def hex_to_bt64(hex_str):
    """将 16 位十六进制字符串转换为 64 位比特字符串"""
    binary = ""
    for i in range(16):
        binary += hex_to_bt4(hex_str[i])
    return binary


# === DES 核心算法 ===

def generate_keys(key_byte):
    """根据 64 位密钥字节生成 16 轮子密钥"""
    key = [0] * 56
    keys = [[] for _ in range(16)]
    loop = [1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1]

    for i in range(7):
        for j in range(8):
            k = 7 - j
            key[i * 8 + j] = key_byte[8 * k + i]

    for i in range(16):
        temp_left = 0
        temp_right = 0
        for _ in range(loop[i]):
            temp_left = key[0]
            temp_right = key[28]
            for k in range(27):
                key[k] = key[k + 1]
                key[28 + k] = key[29 + k]
            key[27] = temp_left
            key[55] = temp_right

        temp_key = [0] * 48
        temp_key[ 0] = key[13]
        temp_key[ 1] = key[16]
        temp_key[ 2] = key[10]
        temp_key[ 3] = key[23]
        temp_key[ 4] = key[ 0]
        temp_key[ 5] = key[ 4]
        temp_key[ 6] = key[ 2]
        temp_key[ 7] = key[27]
        temp_key[ 8] = key[14]
        temp_key[ 9] = key[ 5]
        temp_key[10] = key[20]
        temp_key[11] = key[ 9]
        temp_key[12] = key[22]
        temp_key[13] = key[18]
        temp_key[14] = key[11]
        temp_key[15] = key[ 3]
        temp_key[16] = key[25]
        temp_key[17] = key[ 7]
        temp_key[18] = key[15]
        temp_key[19] = key[ 6]
        temp_key[20] = key[26]
        temp_key[21] = key[19]
        temp_key[22] = key[12]
        temp_key[23] = key[ 1]
        temp_key[24] = key[40]
        temp_key[25] = key[51]
        temp_key[26] = key[30]
        temp_key[27] = key[36]
        temp_key[28] = key[46]
        temp_key[29] = key[54]
        temp_key[30] = key[29]
        temp_key[31] = key[39]
        temp_key[32] = key[50]
        temp_key[33] = key[44]
        temp_key[34] = key[32]
        temp_key[35] = key[47]
        temp_key[36] = key[43]
        temp_key[37] = key[48]
        temp_key[38] = key[38]
        temp_key[39] = key[55]
        temp_key[40] = key[33]
        temp_key[41] = key[52]
        temp_key[42] = key[45]
        temp_key[43] = key[41]
        temp_key[44] = key[49]
        temp_key[45] = key[35]
        temp_key[46] = key[28]
        temp_key[47] = key[31]

        keys[i] = temp_key[:]

    return keys


def init_permute(original_data):
    """初始置换 IP"""
    ip_byte = [0] * 64
    i = 0
    m = 1
    n = 0
    while i < 4:
        j = 7
        k = 0
        while j >= 0:
            ip_byte[i * 8 + k] = original_data[j * 8 + m]
            ip_byte[i * 8 + k + 32] = original_data[j * 8 + n]
            j -= 1
            k += 1
        i += 1
        m += 2
        n += 2
    return ip_byte


def expand_permute(right_data):
    """扩展置换 E（32 位 → 48 位）"""
    ep_byte = [0] * 48
    for i in range(8):
        if i == 0:
            ep_byte[i * 6 + 0] = right_data[31]
        else:
            ep_byte[i * 6 + 0] = right_data[i * 4 - 1]
        ep_byte[i * 6 + 1] = right_data[i * 4 + 0]
        ep_byte[i * 6 + 2] = right_data[i * 4 + 1]
        ep_byte[i * 6 + 3] = right_data[i * 4 + 2]
        ep_byte[i * 6 + 4] = right_data[i * 4 + 3]
        if i == 7:
            ep_byte[i * 6 + 5] = right_data[0]
        else:
            ep_byte[i * 6 + 5] = right_data[i * 4 + 4]
    return ep_byte


def xor(byte_one, byte_two):
    """两个等长比特数组的异或运算"""
    xor_byte = [0] * len(byte_one)
    for i in range(len(byte_one)):
        xor_byte[i] = byte_one[i] ^ byte_two[i]
    return xor_byte


def s_box_permute(expand_byte):
    """S 盒置换（48 位 → 32 位）"""
    s_box_byte = [0] * 32

    s1 = [
        [14, 4, 13, 1, 2, 15, 11, 8, 3, 10, 6, 12, 5, 9, 0, 7],
        [0, 15, 7, 4, 14, 2, 13, 1, 10, 6, 12, 11, 9, 5, 3, 8],
        [4, 1, 14, 8, 13, 6, 2, 11, 15, 12, 9, 7, 3, 10, 5, 0],
        [15, 12, 8, 2, 4, 9, 1, 7, 5, 11, 3, 14, 10, 0, 6, 13],
    ]

    s2 = [
        [15, 1, 8, 14, 6, 11, 3, 4, 9, 7, 2, 13, 12, 0, 5, 10],
        [3, 13, 4, 7, 15, 2, 8, 14, 12, 0, 1, 10, 6, 9, 11, 5],
        [0, 14, 7, 11, 10, 4, 13, 1, 5, 8, 12, 6, 9, 3, 2, 15],
        [13, 8, 10, 1, 3, 15, 4, 2, 11, 6, 7, 12, 0, 5, 14, 9],
    ]

    s3 = [
        [10, 0, 9, 14, 6, 3, 15, 5, 1, 13, 12, 7, 11, 4, 2, 8],
        [13, 7, 0, 9, 3, 4, 6, 10, 2, 8, 5, 14, 12, 11, 15, 1],
        [13, 6, 4, 9, 8, 15, 3, 0, 11, 1, 2, 12, 5, 10, 14, 7],
        [1, 10, 13, 0, 6, 9, 8, 7, 4, 15, 14, 3, 11, 5, 2, 12],
    ]

    s4 = [
        [7, 13, 14, 3, 0, 6, 9, 10, 1, 2, 8, 5, 11, 12, 4, 15],
        [13, 8, 11, 5, 6, 15, 0, 3, 4, 7, 2, 12, 1, 10, 14, 9],
        [10, 6, 9, 0, 12, 11, 7, 13, 15, 1, 3, 14, 5, 2, 8, 4],
        [3, 15, 0, 6, 10, 1, 13, 8, 9, 4, 5, 11, 12, 7, 2, 14],
    ]

    s5 = [
        [2, 12, 4, 1, 7, 10, 11, 6, 8, 5, 3, 15, 13, 0, 14, 9],
        [14, 11, 2, 12, 4, 7, 13, 1, 5, 0, 15, 10, 3, 9, 8, 6],
        [4, 2, 1, 11, 10, 13, 7, 8, 15, 9, 12, 5, 6, 3, 0, 14],
        [11, 8, 12, 7, 1, 14, 2, 13, 6, 15, 0, 9, 10, 4, 5, 3],
    ]

    s6 = [
        [12, 1, 10, 15, 9, 2, 6, 8, 0, 13, 3, 4, 14, 7, 5, 11],
        [10, 15, 4, 2, 7, 12, 9, 5, 6, 1, 13, 14, 0, 11, 3, 8],
        [9, 14, 15, 5, 2, 8, 12, 3, 7, 0, 4, 10, 1, 13, 11, 6],
        [4, 3, 2, 12, 9, 5, 15, 10, 11, 14, 1, 7, 6, 0, 8, 13],
    ]

    s7 = [
        [4, 11, 2, 14, 15, 0, 8, 13, 3, 12, 9, 7, 5, 10, 6, 1],
        [13, 0, 11, 7, 4, 9, 1, 10, 14, 3, 5, 12, 2, 15, 8, 6],
        [1, 4, 11, 13, 12, 3, 7, 14, 10, 15, 6, 8, 0, 5, 9, 2],
        [6, 11, 13, 8, 1, 4, 10, 7, 9, 5, 0, 15, 14, 2, 3, 12],
    ]

    s8 = [
        [13, 2, 8, 4, 6, 15, 11, 1, 10, 9, 3, 14, 5, 0, 12, 7],
        [1, 15, 13, 8, 10, 3, 7, 4, 12, 5, 6, 11, 0, 14, 9, 2],
        [7, 11, 4, 1, 9, 12, 14, 2, 0, 6, 10, 13, 15, 3, 5, 8],
        [2, 1, 14, 7, 4, 10, 8, 13, 15, 12, 9, 0, 3, 5, 6, 11],
    ]

    for m in range(8):
        i = expand_byte[m * 6 + 0] * 2 + expand_byte[m * 6 + 5]
        j = (expand_byte[m * 6 + 1] * 2 * 2 * 2
             + expand_byte[m * 6 + 2] * 2 * 2
             + expand_byte[m * 6 + 3] * 2
             + expand_byte[m * 6 + 4])
        if m == 0:
            binary = get_box_binary(s1[i][j])
        elif m == 1:
            binary = get_box_binary(s2[i][j])
        elif m == 2:
            binary = get_box_binary(s3[i][j])
        elif m == 3:
            binary = get_box_binary(s4[i][j])
        elif m == 4:
            binary = get_box_binary(s5[i][j])
        elif m == 5:
            binary = get_box_binary(s6[i][j])
        elif m == 6:
            binary = get_box_binary(s7[i][j])
        elif m == 7:
            binary = get_box_binary(s8[i][j])

        s_box_byte[m * 4 + 0] = int(binary[0])
        s_box_byte[m * 4 + 1] = int(binary[1])
        s_box_byte[m * 4 + 2] = int(binary[2])
        s_box_byte[m * 4 + 3] = int(binary[3])

    return s_box_byte


def p_permute(s_box_byte):
    """P 盒置换"""
    p_box_permute = [0] * 32
    p_box_permute[ 0] = s_box_byte[15]
    p_box_permute[ 1] = s_box_byte[ 6]
    p_box_permute[ 2] = s_box_byte[19]
    p_box_permute[ 3] = s_box_byte[20]
    p_box_permute[ 4] = s_box_byte[28]
    p_box_permute[ 5] = s_box_byte[11]
    p_box_permute[ 6] = s_box_byte[27]
    p_box_permute[ 7] = s_box_byte[16]
    p_box_permute[ 8] = s_box_byte[ 0]
    p_box_permute[ 9] = s_box_byte[14]
    p_box_permute[10] = s_box_byte[22]
    p_box_permute[11] = s_box_byte[25]
    p_box_permute[12] = s_box_byte[ 4]
    p_box_permute[13] = s_box_byte[17]
    p_box_permute[14] = s_box_byte[30]
    p_box_permute[15] = s_box_byte[ 9]
    p_box_permute[16] = s_box_byte[ 1]
    p_box_permute[17] = s_box_byte[ 7]
    p_box_permute[18] = s_box_byte[23]
    p_box_permute[19] = s_box_byte[13]
    p_box_permute[20] = s_box_byte[31]
    p_box_permute[21] = s_box_byte[26]
    p_box_permute[22] = s_box_byte[ 2]
    p_box_permute[23] = s_box_byte[ 8]
    p_box_permute[24] = s_box_byte[18]
    p_box_permute[25] = s_box_byte[12]
    p_box_permute[26] = s_box_byte[29]
    p_box_permute[27] = s_box_byte[ 5]
    p_box_permute[28] = s_box_byte[21]
    p_box_permute[29] = s_box_byte[10]
    p_box_permute[30] = s_box_byte[ 3]
    p_box_permute[31] = s_box_byte[24]
    return p_box_permute


def finally_permute(end_byte):
    """最终置换 IP^-1"""
    fp_byte = [0] * 64
    fp_byte[ 0] = end_byte[39]
    fp_byte[ 1] = end_byte[ 7]
    fp_byte[ 2] = end_byte[47]
    fp_byte[ 3] = end_byte[15]
    fp_byte[ 4] = end_byte[55]
    fp_byte[ 5] = end_byte[23]
    fp_byte[ 6] = end_byte[63]
    fp_byte[ 7] = end_byte[31]
    fp_byte[ 8] = end_byte[38]
    fp_byte[ 9] = end_byte[ 6]
    fp_byte[10] = end_byte[46]
    fp_byte[11] = end_byte[14]
    fp_byte[12] = end_byte[54]
    fp_byte[13] = end_byte[22]
    fp_byte[14] = end_byte[62]
    fp_byte[15] = end_byte[30]
    fp_byte[16] = end_byte[37]
    fp_byte[17] = end_byte[ 5]
    fp_byte[18] = end_byte[45]
    fp_byte[19] = end_byte[13]
    fp_byte[20] = end_byte[53]
    fp_byte[21] = end_byte[21]
    fp_byte[22] = end_byte[61]
    fp_byte[23] = end_byte[29]
    fp_byte[24] = end_byte[36]
    fp_byte[25] = end_byte[ 4]
    fp_byte[26] = end_byte[44]
    fp_byte[27] = end_byte[12]
    fp_byte[28] = end_byte[52]
    fp_byte[29] = end_byte[20]
    fp_byte[30] = end_byte[60]
    fp_byte[31] = end_byte[28]
    fp_byte[32] = end_byte[35]
    fp_byte[33] = end_byte[ 3]
    fp_byte[34] = end_byte[43]
    fp_byte[35] = end_byte[11]
    fp_byte[36] = end_byte[51]
    fp_byte[37] = end_byte[19]
    fp_byte[38] = end_byte[59]
    fp_byte[39] = end_byte[27]
    fp_byte[40] = end_byte[34]
    fp_byte[41] = end_byte[ 2]
    fp_byte[42] = end_byte[42]
    fp_byte[43] = end_byte[10]
    fp_byte[44] = end_byte[50]
    fp_byte[45] = end_byte[18]
    fp_byte[46] = end_byte[58]
    fp_byte[47] = end_byte[26]
    fp_byte[48] = end_byte[33]
    fp_byte[49] = end_byte[ 1]
    fp_byte[50] = end_byte[41]
    fp_byte[51] = end_byte[ 9]
    fp_byte[52] = end_byte[49]
    fp_byte[53] = end_byte[17]
    fp_byte[54] = end_byte[57]
    fp_byte[55] = end_byte[25]
    fp_byte[56] = end_byte[32]
    fp_byte[57] = end_byte[ 0]
    fp_byte[58] = end_byte[40]
    fp_byte[59] = end_byte[ 8]
    fp_byte[60] = end_byte[48]
    fp_byte[61] = end_byte[16]
    fp_byte[62] = end_byte[56]
    fp_byte[63] = end_byte[24]
    return fp_byte


def enc(data_byte, key_byte):
    """DES 加密单个 64 位块"""
    keys = generate_keys(key_byte)
    ip_byte = init_permute(data_byte)
    ip_left = [0] * 32
    ip_right = [0] * 32
    temp_left = [0] * 32

    for k in range(32):
        ip_left[k] = ip_byte[k]
        ip_right[k] = ip_byte[32 + k]

    for i in range(16):
        for j in range(32):
            temp_left[j] = ip_left[j]
            ip_left[j] = ip_right[j]
        key = [0] * 48
        for m in range(48):
            key[m] = keys[i][m]
        temp_right = xor(p_permute(s_box_permute(xor(expand_permute(ip_right), key))), temp_left)
        for n in range(32):
            ip_right[n] = temp_right[n]

    final_data = [0] * 64
    for i in range(32):
        final_data[i] = ip_right[i]
        final_data[32 + i] = ip_left[i]

    return finally_permute(final_data)


def dec(data_byte, key_byte):
    """DES 解密单个 64 位块"""
    keys = generate_keys(key_byte)
    ip_byte = init_permute(data_byte)
    ip_left = [0] * 32
    ip_right = [0] * 32
    temp_left = [0] * 32

    for k in range(32):
        ip_left[k] = ip_byte[k]
        ip_right[k] = ip_byte[32 + k]

    for i in range(15, -1, -1):
        for j in range(32):
            temp_left[j] = ip_left[j]
            ip_left[j] = ip_right[j]
        key = [0] * 48
        for m in range(48):
            key[m] = keys[i][m]
        temp_right = xor(p_permute(s_box_permute(xor(expand_permute(ip_right), key))), temp_left)
        for n in range(32):
            ip_right[n] = temp_right[n]

    final_data = [0] * 64
    for i in range(32):
        final_data[i] = ip_right[i]
        final_data[32 + i] = ip_left[i]

    return finally_permute(final_data)


# === 公开接口 ===

def _encrypt_with_keys(bt, key_bts):
    """用一组密钥对比特数组进行加密"""
    temp_bt = bt
    for key_bt in key_bts:
        key_len = len(key_bt)
        for x in range(key_len):
            temp_bt = enc(temp_bt, key_bt[x])
    return temp_bt


def str_enc(data, first_key, second_key, third_key):
    """
    DES 加密字符串，返回十六进制字符串
    行为与 JS 的 strEnc 完全一致
    """
    # None 保护：将 None 密钥视为空字符串
    first_key = first_key or ""
    second_key = second_key or ""
    third_key = third_key or ""
    data = data or ""
    if not data:
        return ""
    leng = len(data)
    enc_data = ""
    first_key_bt = None
    second_key_bt = None
    third_key_bt = None
    first_length = 0
    second_length = 0
    third_length = 0

    if first_key is not None and first_key != "":
        first_key_bt = get_key_bytes(first_key)
        first_length = len(first_key_bt)
    if second_key is not None and second_key != "":
        second_key_bt = get_key_bytes(second_key)
        second_length = len(second_key_bt)
    if third_key is not None and third_key != "":
        third_key_bt = get_key_bytes(third_key)
        third_length = len(third_key_bt)

    if leng > 0:
        if leng < 4:
            bt = str_to_bt(data)
            enc_byte = None
            if (first_key is not None and first_key != "" and
                    second_key is not None and second_key != "" and
                    third_key is not None and third_key != ""):
                temp_bt = bt
                for x in range(first_length):
                    temp_bt = enc(temp_bt, first_key_bt[x])
                for y in range(second_length):
                    temp_bt = enc(temp_bt, second_key_bt[y])
                for z in range(third_length):
                    temp_bt = enc(temp_bt, third_key_bt[z])
                enc_byte = temp_bt
            else:
                if (first_key is not None and first_key != "" and
                        second_key is not None and second_key != ""):
                    temp_bt = bt
                    for x in range(first_length):
                        temp_bt = enc(temp_bt, first_key_bt[x])
                    for y in range(second_length):
                        temp_bt = enc(temp_bt, second_key_bt[y])
                    enc_byte = temp_bt
                else:
                    if first_key is not None and first_key != "":
                        temp_bt = bt
                        for x in range(first_length):
                            temp_bt = enc(temp_bt, first_key_bt[x])
                        enc_byte = temp_bt
            if enc_byte is None: enc_byte = temp_bt if 'temp_bt' in dir() else temp_byte
            enc_data = bt64_to_hex(enc_byte)
        else:
            iterator = int(leng / 4)
            remainder = leng % 4

            for i in range(iterator):
                temp_data = data[i * 4:i * 4 + 4]
                temp_byte = str_to_bt(temp_data)
                enc_byte = None
                if (first_key is not None and first_key != "" and
                        second_key is not None and second_key != "" and
                        third_key is not None and third_key != ""):
                    temp_bt = temp_byte
                    for x in range(first_length):
                        temp_bt = enc(temp_bt, first_key_bt[x])
                    for y in range(second_length):
                        temp_bt = enc(temp_bt, second_key_bt[y])
                    for z in range(third_length):
                        temp_bt = enc(temp_bt, third_key_bt[z])
                    enc_byte = temp_bt
                else:
                    if (first_key is not None and first_key != "" and
                            second_key is not None and second_key != ""):
                        temp_bt = temp_byte
                        for x in range(first_length):
                            temp_bt = enc(temp_bt, first_key_bt[x])
                        for y in range(second_length):
                            temp_bt = enc(temp_bt, second_key_bt[y])
                        enc_byte = temp_bt
                    else:
                        if first_key is not None and first_key != "":
                            temp_bt = temp_byte
                            for x in range(first_length):
                                temp_bt = enc(temp_bt, first_key_bt[x])
                            enc_byte = temp_bt
                if enc_byte is None: enc_byte = temp_bt if 'temp_bt' in dir() else temp_byte
                enc_data += bt64_to_hex(enc_byte)

            if remainder > 0:
                remainder_data = data[iterator * 4:leng]
                temp_byte = str_to_bt(remainder_data)
                enc_byte = None
                if (first_key is not None and first_key != "" and
                        second_key is not None and second_key != "" and
                        third_key is not None and third_key != ""):
                    temp_bt = temp_byte
                    for x in range(first_length):
                        temp_bt = enc(temp_bt, first_key_bt[x])
                    for y in range(second_length):
                        temp_bt = enc(temp_bt, second_key_bt[y])
                    for z in range(third_length):
                        temp_bt = enc(temp_bt, third_key_bt[z])
                    enc_byte = temp_bt
                else:
                    if (first_key is not None and first_key != "" and
                            second_key is not None and second_key != ""):
                        temp_bt = temp_byte
                        for x in range(first_length):
                            temp_bt = enc(temp_bt, first_key_bt[x])
                        for y in range(second_length):
                            temp_bt = enc(temp_bt, second_key_bt[y])
                        enc_byte = temp_bt
                    else:
                        if first_key is not None and first_key != "":
                            temp_bt = temp_byte
                            for x in range(first_length):
                                temp_bt = enc(temp_bt, first_key_bt[x])
                            enc_byte = temp_bt
                if enc_byte is None: enc_byte = temp_bt if 'temp_bt' in dir() else temp_byte
                enc_data += bt64_to_hex(enc_byte)

    return enc_data


def str_dec(data, first_key, second_key, third_key):
    """
    DES 解密十六进制字符串，返回原始字符串
    行为与 JS 的 strDec 完全一致
    """
    leng = len(data)
    dec_str = ""
    first_key_bt = None
    second_key_bt = None
    third_key_bt = None
    first_length = 0
    second_length = 0
    third_length = 0

    if first_key is not None and first_key != "":
        first_key_bt = get_key_bytes(first_key)
        first_length = len(first_key_bt)
    if second_key is not None and second_key != "":
        second_key_bt = get_key_bytes(second_key)
        second_length = len(second_key_bt)
    if third_key is not None and third_key != "":
        third_key_bt = get_key_bytes(third_key)
        third_length = len(third_key_bt)

    iterator = int(leng / 16)

    for i in range(iterator):
        temp_data = data[i * 16:i * 16 + 16]
        str_byte = hex_to_bt64(temp_data)
        int_byte = [0] * 64
        for j in range(64):
            int_byte[j] = int(str_byte[j])

        dec_byte = None
        if (first_key is not None and first_key != "" and
                second_key is not None and second_key != "" and
                third_key is not None and third_key != ""):
            temp_bt = int_byte
            for x in range(third_length - 1, -1, -1):
                temp_bt = dec(temp_bt, third_key_bt[x])
            for y in range(second_length - 1, -1, -1):
                temp_bt = dec(temp_bt, second_key_bt[y])
            for z in range(first_length - 1, -1, -1):
                temp_bt = dec(temp_bt, first_key_bt[z])
            dec_byte = temp_bt
        else:
            if (first_key is not None and first_key != "" and
                    second_key is not None and second_key != ""):
                temp_bt = int_byte
                for x in range(second_length - 1, -1, -1):
                    temp_bt = dec(temp_bt, second_key_bt[x])
                for y in range(first_length - 1, -1, -1):
                    temp_bt = dec(temp_bt, first_key_bt[y])
                dec_byte = temp_bt
            else:
                if first_key is not None and first_key != "":
                    temp_bt = int_byte
                    for x in range(first_length - 1, -1, -1):
                        temp_bt = dec(temp_bt, first_key_bt[x])
                    dec_byte = temp_bt
        dec_str += byte_to_string(dec_byte)

    return dec_str


