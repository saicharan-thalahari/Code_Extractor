package com.example.util;

public class Validator {
    public static boolean isValidAccountId(String id) {
        return id != null && !id.isEmpty();
    }
}
