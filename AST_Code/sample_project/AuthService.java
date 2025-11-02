package com.example.auth;

import com.example.service.UserService;
import com.example.util.Helper;

public class AuthService {
    private UserService us = new UserService();

    public boolean authenticate(String id) {
        Helper.log("Authenticating " + id);
        // pretend to check credentials
        return true;
    }
}
