import unittest

import main


class AuthFlowTests(unittest.TestCase):
    def test_send_smtp_email_function_exists(self):
        self.assertTrue(hasattr(main, 'send_smtp_email'))

    def test_user_manager_supports_register_and_login(self):
        self.assertTrue(hasattr(main, 'USERS'))
        self.assertTrue(hasattr(main, 'register_user'))
        self.assertTrue(hasattr(main, 'login_user'))


if __name__ == '__main__':
    unittest.main()
