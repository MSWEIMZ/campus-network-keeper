"""DES 加密模块测试（纯函数，无外部依赖）"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from des_crypto import str_enc, str_dec


class TestStrEnc:
    """str_enc 加密函数测试"""

    def test_returns_hex_string(self):
        """加密结果应为大写十六进制字符串"""
        result = str_enc("test", "1", "2", "3")
        assert isinstance(result, str)
        assert len(result) > 0
        # 每个字符都应是合法的十六进制
        assert all(c in "0123456789ABCDEF" for c in result), f"非法字符: {result}"

    def test_encryption_length_multiple_of_16(self):
        """加密结果长度应为 16 的倍数（每4字符→64bit→16hex）"""
        for data in ["", "a", "ab", "abc", "abcd", "abcdefgh", "1234567890"]:
            result = str_enc(data, "1", "2", "3")
            assert len(result) % 16 == 0, f"data='{data}' len={len(result)}"

    def test_deterministic(self):
        """相同输入应产生相同输出（DES 是确定性的）"""
        r1 = str_enc("hello", "k1", "k2", "k3")
        r2 = str_enc("hello", "k1", "k2", "k3")
        assert r1 == r2

    def test_different_keys_produce_different_output(self):
        """不同密钥应产生不同密文"""
        r1 = str_enc("test", "1", "2", "3")
        r2 = str_enc("test", "a", "b", "c")
        assert r1 != r2

    def test_empty_string(self):
        """空字符串应返回空字符串"""
        result = str_enc("", "1", "2", "3")
        assert result == ""

    def test_none_keys_treated_as_empty(self):
        """None 密钥应等同于空密钥（不加密）"""
        result_none = str_enc("test", None, None, None)
        result_empty = str_enc("test", "", "", "")
        # 两者行为应该一致
        assert result_none == result_empty


class TestStrDec:
    """str_dec 解密函数测试"""

    def test_roundtrip_single_key(self):
        """加密→解密应还原原文（单密钥）"""
        original = "test"
        encrypted = str_enc(original, "1", "", "")
        decrypted = str_dec(encrypted, "1", "", "")
        assert decrypted.rstrip('\x00') == original

    def test_roundtrip_triple_key(self):
        """加密→解密应还原原文（三密钥，DLUT CAS 模式）"""
        original = "testuser123@testpass456LT-abc123"
        encrypted = str_enc(original, "1", "2", "3")
        decrypted = str_dec(encrypted, "1", "2", "3")
        assert decrypted.rstrip('\x00') == original

    def test_roundtrip_chinese(self):
        """中文字符加解密往返"""
        original = "你好"
        encrypted = str_enc(original, "key1", "key2", "key3")
        decrypted = str_dec(encrypted, "key1", "key2", "key3")
        assert decrypted.rstrip('\x00') == original

    def test_roundtrip_long_string(self):
        """较长字符串加解密往返"""
        original = "a" * 100
        encrypted = str_enc(original, "x", "y", "z")
        decrypted = str_dec(encrypted, "x", "y", "z")
        assert decrypted.rstrip('\x00') == original


class TestDlutCasIntegration:
    """模拟 DLUT CAS 认证场景的集成测试"""

    def test_cas_rsa_field_generation(self):
        """模拟 CAS 登录中的 rsa 字段生成
        rsa = strEnc(username + password + lt, '1', '2', '3')
        """
        username = "testuser123"
        password = "testpass123"
        lt = "LT-1234567890abcdef-cas"

        rsa = str_enc(username + password + lt, "1", "2", "3")

        # rsa 字段应为非空十六进制字符串
        assert len(rsa) > 0
        assert all(c in "0123456789ABCDEF" for c in rsa)

        # 用相同参数应产生相同结果
        rsa2 = str_enc(username + password + lt, "1", "2", "3")
        assert rsa == rsa2
